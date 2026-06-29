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
        self.simulated = (not self.settings.has_cerebras) or self.settings.force_simulated
        # Populated after stream_tokens() finishes: authoritative usage from the
        # provider (e.g. {"completion_tokens": N}) for an accurate tokens/sec.
        self.last_usage: Optional[dict[str, Any]] = None

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
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """Yield content token chunks (for the speed-comparison panel).

        Requests `stream_options.include_usage` so the provider reports the exact
        `completion_tokens`, stored on `self.last_usage` for an accurate tokens/sec
        (we fall back to counting streamed chunks if usage isn't returned).
        """
        self.last_usage = None
        if self.simulated:
            n = 0
            async for chunk in _simulated_stream(self.model):
                n += 1
                yield chunk
            self.last_usage = {"completion_tokens": n}
            return

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if reasoning_effort:
            payload["reasoning_effort"] = reasoning_effort
        if max_tokens:
            payload["max_tokens"] = max_tokens
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
                    except json.JSONDecodeError:
                        continue
                    if obj.get("usage"):
                        self.last_usage = obj["usage"]
                    choices = obj.get("choices") or []
                    if not choices:
                        continue
                    # Gemma 4 streams chain-of-thought under `reasoning` and the
                    # final answer under `content`. Surface both so the race shows
                    # Cerebras ripping through reasoning + answer (and counts every
                    # token toward tokens/sec).
                    d = choices[0].get("delta") or {}
                    delta = d.get("content") or d.get("reasoning") or d.get("reasoning_content")
                    if delta:
                        yield delta


# --------------------------------------------------------------------------- #
# Simulated (offline) scripted agent - scenario-driven
# --------------------------------------------------------------------------- #
def _active_scenario():
    """The incident pack currently loaded in the mock backend."""
    from app.pipeline.mock_backend import MockBackend

    return MockBackend.instance().scenario


def _simulated_completion(step: Optional[str], json_object: bool) -> ChatResult:
    step = step or ""
    sim = _active_scenario().sim

    def res(content: str = "", tcs: Optional[list[ToolCall]] = None) -> ChatResult:
        return ChatResult(content=content, tool_calls=tcs or [], latency_ms=11.0,
                          completion_tokens=max(1, len(content) // 4), model="gemma-4-31b (sim)",
                          simulated=True)

    def calls(key: str) -> list[ToolCall]:
        return [_mk_toolcall(name, dict(args)) for name, args in sim.get(key, [])]

    if step == "vision":
        return res(sim["vision"])
    if step == "triage":
        return res(sim["triage"])
    if step.endswith(":act"):
        spec = step.split(":", 1)[0]
        return res(tcs=calls(f"{spec}_act"))
    if step.endswith(":summary"):
        spec = step.split(":", 1)[0]
        return res(sim.get(f"{spec}_summary", "(no finding)"))
    if step.startswith("race:"):
        action = step.split(":", 1)[1]
        cand = next((c for c in sim["candidates"] if c["action"] == action), None)
        if cand is None:
            cand = sim["candidates"][-1]
        return res(content=json.dumps({
            "action": cand["action"], "predicted_green": cand["predicted_green"],
            "risk_tier": cand["risk_tier"], "confidence": cand["confidence"],
            "predicted_outcome": cand["predicted_outcome"]}))
    if step == "immunize":
        return res(content=json.dumps(sim["guardrail"]))
    if step == "synthesis" or json_object:
        return res(content=json.dumps(sim["synthesis"]))
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
