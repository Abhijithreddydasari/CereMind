"""Side-by-side incident comparison: Cerebras vs a GPU baseline.

Streams two full CereMind investigation runs over one SSE channel, so the UI can
compare the same incident system on Cerebras and on the configured Modal/GPU
baseline. The baseline remains clearly labeled when simulated.
"""
from __future__ import annotations

import asyncio
import json
import time

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.agents.commander import Commander
from app.agents.schemas import AgentEvent, Incident, IncidentTrigger
from app.config import get_settings
from app.llm.baseline_client import BaselineClient
from app.llm.cerebras_client import CerebrasClient
from app.pipeline.mock_backend import MockBackend
from app.pipeline.scenarios import get_scenario

router = APIRouter(prefix="/api/speed", tags=["speed"])


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


def _trigger_for_scenario(scenario_id: str | None) -> IncidentTrigger:
    s = get_scenario(scenario_id)
    return IncidentTrigger(
        source="webhook",
        title=s.title,
        job_id=s.job_id,
        failed_task=s.failed_task,
        summary=s.summary,
        scenario_id=s.id,
        attach_seeded_snapshot=True,
    )


def _format_event(ev: AgentEvent) -> str:
    label = ev.type.replace("_", " ").upper()
    actor = ev.actor or "system"
    title = ev.title or label
    detail = (ev.detail or "").strip()
    if len(detail) > 520:
        detail = detail[:517] + "..."
    return f"[{label}] {actor}: {title}" + (f"\n{detail}\n\n" if detail else "\n\n")


def _completion_tokens(ev: AgentEvent) -> int:
    """Provider completion-token count attached by the agent layer."""
    try:
        return max(0, int(ev.data.get("_llm_completion_tokens") or 0))
    except (TypeError, ValueError):
        return 0


@router.get("/info")
async def info():
    s = get_settings()
    return {
        "cerebras": {"model": s.cerebras_model, "simulated": not s.has_cerebras},
        "baseline": {"label": s.baseline_label, "model": s.baseline_model or "simulated",
                     "simulated": not s.has_baseline, "sim_tps": s.baseline_sim_tps},
    }


@router.get("/stream")
async def stream(scenario_id: str | None = None):
    cerebras = CerebrasClient()
    baseline = BaselineClient()
    scenario = get_scenario(scenario_id)

    async def race():
        yield _sse({"type": "start", "cerebras_model": cerebras.model,
                    "baseline_label": baseline.label,
                    "cerebras_simulated": cerebras.simulated,
                    "baseline_simulated": baseline.simulated,
                    "scenario_id": scenario.id,
                    "cost_per_min": scenario.cost_per_min,
                    "mode": "incident"})

        state = {
            "cerebras": {"tokens": 0, "events": 0, "t0": None, "t_first": None,
                         "last_event": None, "ttft": None, "done": False},
            "baseline": {"tokens": 0, "events": 0, "t0": None, "t_first": None,
                         "last_event": None, "ttft": None, "done": False},
        }
        queue: asyncio.Queue = asyncio.Queue()

        def tokens_per_sec(tokens: int, t_start, t_end) -> float:
            if not t_start or tokens <= 0:
                return 0.0
            dt = t_end - t_start
            return tokens / dt if dt > 0 else 0.0

        async def run(engine: str, commander: Commander):
            # Both runs intentionally inspect the same incident pack.
            MockBackend.instance().load_scenario(scenario.id)
            incident = Incident(trigger=_trigger_for_scenario(scenario.id))
            st = state[engine]
            st["t0"] = time.perf_counter()
            st["last_event"] = st["t0"]
            error: str | None = None

            async def put_event(ev: AgentEvent, token_delta: int = 0):
                now = time.perf_counter()
                if token_delta > 0 and st["t_first"] is None:
                    st["t_first"] = now
                    st["ttft"] = (now - st["t0"]) * 1000.0  # time-to-first-token (ms)
                st["events"] += 1
                st["tokens"] += token_delta
                st["last_event"] = now
                elapsed = now - st["t0"]
                tps = tokens_per_sec(st["tokens"], st["t0"], now)
                if token_delta > 0:
                    await queue.put({
                        "type": "token", "engine": engine,
                        "tokens": st["tokens"],
                        "token_delta": token_delta,
                        "elapsed_ms": round(elapsed * 1000, 1),
                        "ttft_ms": round(st["ttft"] or 0.0, 1),
                        "tps": round(tps, 1),
                    })
                await queue.put({
                    "type": "agent_event", "engine": engine,
                    "event": ev.model_dump(),
                    "chunk": _format_event(ev),
                    "tokens": st["tokens"],
                    "events": st["events"],
                    "elapsed_ms": round(elapsed * 1000, 1),
                    "ttft_ms": round(st["ttft"] or 0.0, 1),
                    "tps": round(tps, 1),
                })

            async def heartbeat():
                # Modal cold starts and long Gemma generations can otherwise look
                # frozen because the baseline uses non-streaming agent calls.
                first_wait = 8.0 if engine == "baseline" else 15.0
                repeat_wait = 12.0 if engine == "baseline" else 20.0
                await asyncio.sleep(first_wait)
                while not st["done"]:
                    now = time.perf_counter()
                    if st["last_event"] and now - st["last_event"] >= first_wait:
                        label = "Modal GPU baseline" if engine == "baseline" else "Cerebras"
                        ev = AgentEvent(
                            incident_id=incident.id,
                            type="thought",
                            actor="system",
                            title=f"Waiting on {label}",
                            detail=(
                                "The request is still active. Modal may be cold-starting the GPU "
                                "container."
                                if engine == "baseline"
                                else "The request is still active; waiting for the next model step."
                            ),
                        )
                        await put_event(ev)
                    await asyncio.sleep(repeat_wait)

            heartbeat_task = asyncio.create_task(heartbeat())
            try:
                async for ev in commander.investigate(incident):
                    await put_event(ev, _completion_tokens(ev))
            except Exception as exc:  # don't let one engine hang the whole race
                error = f"{type(exc).__name__}: {exc}"
            t_end = time.perf_counter()
            elapsed = t_end - st["t0"]
            st["done"] = True
            heartbeat_task.cancel()
            await asyncio.gather(heartbeat_task, return_exceptions=True)
            await queue.put({"type": "engine_done", "engine": engine,
                             "elapsed_ms": round(elapsed * 1000, 1), "tokens": st["tokens"],
                             "events": st["events"],
                             "ttft_ms": round(st["ttft"] or 0.0, 1),
                             "tps": round(tokens_per_sec(st["tokens"], st["t0"], t_end), 1),
                             "error": error})

        tasks = [
            asyncio.create_task(run(
                "cerebras", Commander(cerebras, f"cerebras:{cerebras.model}"))),
            asyncio.create_task(run(
                "baseline", Commander(baseline, baseline.label))),
        ]

        done_count = 0
        while done_count < 2:
            evt = await queue.get()
            yield _sse(evt)
            if evt["type"] == "engine_done":
                done_count += 1
        await asyncio.gather(*tasks, return_exceptions=True)
        yield _sse({"type": "done"})

    return StreamingResponse(race(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
