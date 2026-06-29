"""Side-by-side speed comparison: Cerebras vs a GPU baseline.

Streams both engines token-by-token over one SSE channel with live tokens/sec
and wall-clock timings, so the UI can render two racing panes. The baseline is
always labeled as representative.
"""
from __future__ import annotations

import asyncio
import json
import time

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.config import get_settings
from app.llm.baseline_client import BaselineClient
from app.llm.cerebras_client import CerebrasClient

router = APIRouter(prefix="/api/speed", tags=["speed"])

# A meatier prompt so both engines generate a few hundred tokens - long enough
# for a stable tokens/sec read and a visually clear race (very short answers are
# dominated by time-to-first-token noise).
PROMPT = (
    "You are CereMind, an autonomous incident commander. A nightly ETL pipeline's "
    "`transform` task was OOMKilled after a cost-optimization bot cut its worker memory "
    "from 8192MB to 2048MB. In a thorough paragraph, explain the root cause, the exact "
    "remediation steps, how to verify the job is healthy after the fix, and one preventive "
    "guardrail that stops this class of failure from recurring."
)
# Same cap for both engines so the comparison is apples-to-apples.
MAX_TOKENS = 400


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


@router.get("/info")
async def info():
    s = get_settings()
    return {
        "cerebras": {"model": s.cerebras_model, "simulated": not s.has_cerebras},
        "baseline": {"label": s.baseline_label, "model": s.baseline_model or "simulated",
                     "simulated": not s.has_baseline, "sim_tps": s.baseline_sim_tps},
    }


@router.get("/stream")
async def stream():
    cerebras = CerebrasClient()
    baseline = BaselineClient()
    messages = [{"role": "user", "content": PROMPT}]

    async def race():
        yield _sse({"type": "start", "cerebras_model": cerebras.model,
                    "baseline_label": baseline.label,
                    "cerebras_simulated": cerebras.simulated,
                    "baseline_simulated": baseline.simulated})

        state = {
            "cerebras": {"text": "", "chunks": 0, "t0": None, "t_first": None,
                         "ttft": None, "done": False},
            "baseline": {"text": "", "chunks": 0, "t0": None, "t_first": None,
                         "ttft": None, "done": False},
        }
        clients = {"cerebras": cerebras, "baseline": baseline}
        queue: asyncio.Queue = asyncio.Queue()

        def decode_tps(tokens: int, t_first, t_end) -> float:
            # Pure generation speed: tokens after the first / decode window. Excludes
            # time-to-first-token (queue + network + prefill) so the headline number
            # reflects inference throughput, not the user's distance to the datacenter.
            if not t_first or tokens < 2:
                return 0.0
            dt = t_end - t_first
            return (tokens - 1) / dt if dt > 0 else 0.0

        async def run(engine: str, gen):
            st = state[engine]
            st["t0"] = time.perf_counter()
            error: str | None = None
            try:
                async for chunk in gen:
                    now = time.perf_counter()
                    if st["t_first"] is None:
                        st["t_first"] = now
                        st["ttft"] = (now - st["t0"]) * 1000.0  # time-to-first-token (ms)
                    st["text"] += chunk
                    st["chunks"] += 1
                    # Providers pack several tokens per SSE chunk, so estimate live
                    # token count from characters (~4 chars/token). The final number
                    # is corrected to the provider's exact completion_tokens below.
                    est = max(st["chunks"], round(len(st["text"]) / 4))
                    elapsed = now - st["t0"]
                    tps = decode_tps(est, st["t_first"], now)
                    await queue.put({"type": "token", "engine": engine, "chunk": chunk,
                                     "tokens": est, "elapsed_ms": round(elapsed * 1000, 1),
                                     "ttft_ms": round(st["ttft"], 1), "tps": round(tps, 1)})
            except Exception as exc:  # don't let one engine hang the whole race
                error = f"{type(exc).__name__}: {exc}"
            t_end = time.perf_counter()
            elapsed = t_end - st["t0"]
            st["done"] = True
            # Prefer the provider's exact completion_tokens; fall back to chunk count.
            usage = clients[engine].last_usage or {}
            tokens = int(usage.get("completion_tokens") or st["chunks"])
            await queue.put({"type": "engine_done", "engine": engine,
                             "elapsed_ms": round(elapsed * 1000, 1), "tokens": tokens,
                             "ttft_ms": round(st["ttft"] or 0.0, 1),
                             "tps": round(decode_tps(tokens, st["t_first"], t_end), 1),
                             "error": error})

        tasks = [
            asyncio.create_task(run("cerebras", cerebras.stream_tokens(
                messages, reasoning_effort="low", max_tokens=MAX_TOKENS))),
            asyncio.create_task(run("baseline", baseline.stream_tokens(
                messages, max_tokens=MAX_TOKENS))),
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
