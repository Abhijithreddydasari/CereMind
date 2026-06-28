"""Cerebras (Gemma 4 31B) chat client.

Real path: OpenAI-compatible /chat/completions over httpx, with strict tool
calling, image content parts, and the reasoning_effort knob.

Simulated path: when CEREBRAS_API_KEY is unset, a deterministic scripted agent
returns responses in the same normalized shape, so the entire CereMind UX is
demoable offline. The orchestrator code is identical in both cases.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Optional

import httpx

from app.config import get_settings


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ChatResult:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    latency_ms: float = 0.0
    completion_tokens: int = 0
    model: str = ""
    simulated: bool = False


def _mk_toolcall(name: str, args: dict[str, Any]) -> ToolCall:
    return ToolCall(id=f"call_{uuid.uuid4().hex[:8]}", name=name, arguments=args)


class CerebrasClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.model = self.settings.cerebras_model
        self.simulated = not self.settings.has_cerebras

    # ----------------------------------------------------------------- chat
    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        reasoning_effort: Optional[str] = None,
        step: Optional[str] = None,
        json_object: bool = False,
    ) -> ChatResult:
        if self.simulated:
            return _simulated_completion(step, json_object)
        return await self._real_completion(messages, tools, reasoning_effort, json_object)

    async def _real_completion(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]],
        reasoning_effort: Optional[str],
        json_object: bool,
    ) -> ChatResult:
        payload: dict[str, Any] = {"model": self.model, "messages": messages}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if reasoning_effort:
            payload["reasoning_effort"] = reasoning_effort
        if json_object:
            payload["response_format"] = {"type": "json_object"}

        url = f"{self.settings.cerebras_base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {self.settings.cerebras_api_key}"}
        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
        latency = (time.perf_counter() - t0) * 1000.0

        choice = data["choices"][0]["message"]
        tool_calls: list[ToolCall] = []
        for tc in choice.get("tool_calls") or []:
            fn = tc.get("function", {})
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(ToolCall(id=tc.get("id", _mk_toolcall(fn.get("name", ""), {}).id),
                                       name=fn.get("name", ""), arguments=args))
        usage = data.get("usage", {})
        return ChatResult(
            content=choice.get("content") or "",
            tool_calls=tool_calls,
            latency_ms=latency,
            completion_tokens=int(usage.get("completion_tokens", 0)),
            model=data.get("model", self.model),
            simulated=False,
        )

    # ------------------------------------------------------------- streaming
    async def stream_tokens(
        self,
        messages: list[dict[str, Any]],
        reasoning_effort: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Yield content token chunks (for the speed-comparison panel)."""
        if self.simulated:
            async for chunk in _simulated_stream(self.model):
                yield chunk
            return

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }
        if reasoning_effort:
            payload["reasoning_effort"] = reasoning_effort
        url = f"{self.settings.cerebras_base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {self.settings.cerebras_api_key}"}
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                        delta = obj["choices"][0]["delta"].get("content")
                        if delta:
                            yield delta
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue


# --------------------------------------------------------------------------- #
# Simulated (offline) scripted agent
# --------------------------------------------------------------------------- #
def _simulated_completion(step: Optional[str], json_object: bool) -> ChatResult:
    from app.pipeline.seed import CULPRIT_CHANGE_ID, JOB_ID

    step = step or ""

    def res(content: str = "", tcs: Optional[list[ToolCall]] = None) -> ChatResult:
        return ChatResult(content=content, tool_calls=tcs or [], latency_ms=11.0,
                          completion_tokens=max(1, len(content) // 4), model="gemma-4-31b (sim)",
                          simulated=True)

    if step == "vision":
        return res(
            "The attached snapshot shows the acmeshop_nightly_etl DAG with ingest green, "
            "transform RED (FAILED, OOMKilled), and load skipped. The memory panel is "
            "pegged at a 2048MB worker_memory_limit - a strong signal of a memory cap, "
            "not a data problem."
        )
    if step == "triage":
        return res(
            "A scheduled run of acmeshop_nightly_etl failed at the transform task. "
            "I'll engage the telemetry, change, and knowledge specialists, then synthesize."
        )
    if step == "telemetry:act":
        return res(tcs=[
            _mk_toolcall("get_job_runs", {"job_id": JOB_ID, "limit": 5}),
            _mk_toolcall("get_job_logs", {}),
            _mk_toolcall("get_metrics", {"task_id": "transform", "metric": "memory_mb"}),
        ])
    if step == "telemetry:summary":
        return res(
            "transform was OOMKilled: worker memory pegged at the 2048MB limit, while "
            "the last 3 nightly runs succeeded with a ~6.9GB peak. The memory ceiling, "
            "not the data, is the problem."
        )
    if step == "change:act":
        return res(tcs=[
            _mk_toolcall("list_recent_config_changes", {"limit": 5}),
            _mk_toolcall("config_diff", {"change_id": CULPRIT_CHANGE_ID}),
        ])
    if step == "change:summary":
        return res(
            f"Config change {CULPRIT_CHANGE_ID} by costopt-bot ~1h ago cut "
            "transform worker_memory_mb from 8192 to 2048 - immediately before the failure."
        )
    if step == "knowledge:act":
        return res(tcs=[
            _mk_toolcall("query_runbook", {"query": "transform task OOMKilled memory limit exceeded"}),
            _mk_toolcall("find_similar_failures", {"query": "nightly etl transform OOM after config change"}),
        ])
    if step == "knowledge:summary":
        return res(
            "The OOM runbook and past incident INC-1042 agree: revert the memory-cutting "
            "config change (or raise the limit) and rerun. The failure is deterministic, "
            "so a plain rerun would just fail again."
        )
    if step == "synthesis" or json_object:
        payload = {
            "root_cause": (
                "Config change " + CULPRIT_CHANGE_ID + " reduced transform worker_memory_mb "
                "from 8192 to 2048, causing the transform task to be OOMKilled."
            ),
            "confidence": 0.93,
            "hypotheses": [
                {
                    "claim": "Lowered worker memory (8192->2048MB) caused transform OOMKill.",
                    "likelihood": 0.93,
                    "evidence": [
                        {"source": "job_log", "ref": "run_2004",
                         "detail": "transform OOMKilled: memory limit 2048MB exceeded"},
                        {"source": "metrics", "ref": "transform.memory_mb",
                         "detail": "Memory pegged at 2048MB limit vs ~6.9GB healthy peak"},
                        {"source": "config_change", "ref": CULPRIT_CHANGE_ID,
                         "detail": "worker_memory_mb 8192->2048 by costopt-bot 1h before failure"},
                        {"source": "incident", "ref": "INC-1042",
                         "detail": "Identical past OOM resolved by reverting the memory change"},
                    ],
                },
                {
                    "claim": "Transient/data-volume issue (rerun would fix).",
                    "likelihood": 0.05,
                    "evidence": [
                        {"source": "runbook", "ref": "rb_oom_transform",
                         "detail": "Failure is deterministic, not transient; plain rerun fails again"},
                    ],
                },
            ],
            "proposed_actions": [
                {"action": "revert_config", "args": {"change_id": CULPRIT_CHANGE_ID},
                 "risk_tier": 2,
                 "rationale": "Restore worker_memory_mb to 8192 by reverting the offending change."},
                {"action": "rerun_job", "args": {"job_id": JOB_ID}, "risk_tier": 2,
                 "rationale": "Rerun the nightly ETL to verify recovery after the fix."},
            ],
        }
        return res(content=json.dumps(payload))
    return res("Acknowledged.")


async def _simulated_stream(model: str) -> AsyncGenerator[str, None]:
    import asyncio

    text = (
        "Root cause: config change chg_8f2a1c cut transform worker memory from "
        "8192MB to 2048MB, so the transform task was OOMKilled. Recommended fix: "
        "revert the change to restore 8192MB and rerun the nightly ETL; the failure "
        "is deterministic so a plain rerun would fail again."
    )
    # Cerebras-like ultra-fast cadence: ~1850 tok/s.
    for word in text.split(" "):
        yield word + " "
        await asyncio.sleep(1.0 / 420.0)
