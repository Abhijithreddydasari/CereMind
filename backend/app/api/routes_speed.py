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

PROMPT = (
    "A nightly ETL job's transform task was OOMKilled after a config change cut worker "
    "memory from 8192MB to 2048MB. In 3-4 sentences, state the root cause and the fix."
)


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
            "cerebras": {"text": "", "tokens": 0, "t0": None, "done": False},
            "baseline": {"text": "", "tokens": 0, "t0": None, "done": False},
        }
        queue: asyncio.Queue = asyncio.Queue()

        async def run(engine: str, gen):
            state[engine]["t0"] = time.perf_counter()
            async for chunk in gen:
                st = state[engine]
                st["text"] += chunk
                st["tokens"] += 1
                elapsed = time.perf_counter() - st["t0"]
                tps = st["tokens"] / elapsed if elapsed > 0 else 0.0
                await queue.put({"type": "token", "engine": engine, "chunk": chunk,
                                 "tokens": st["tokens"], "elapsed_ms": round(elapsed * 1000, 1),
                                 "tps": round(tps, 1)})
            st = state[engine]
            elapsed = time.perf_counter() - st["t0"]
            st["done"] = True
            await queue.put({"type": "engine_done", "engine": engine,
                             "elapsed_ms": round(elapsed * 1000, 1), "tokens": st["tokens"],
                             "tps": round(st["tokens"] / elapsed if elapsed > 0 else 0, 1)})

        tasks = [
            asyncio.create_task(run("cerebras", cerebras.stream_tokens(messages,
                                                                       reasoning_effort="low"))),
            asyncio.create_task(run("baseline", baseline.stream_tokens(messages))),
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
