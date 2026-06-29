"""GPU baseline client for the side-by-side speed comparison.

Streams from any OpenAI-compatible endpoint when configured; otherwise simulates
a representative GPU token rate so the comparison still renders. The UI always
labels this pane as a representative baseline to stay honest.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from typing import Any, AsyncGenerator

import httpx

from app.config import get_settings
from app.llm.cerebras_client import ChatResult, ToolCall, _simulated_completion


def _mk_toolcall(name: str, args: dict[str, Any]) -> ToolCall:
    return ToolCall(id=f"call_{uuid.uuid4().hex[:8]}", name=name, arguments=args)


def _text_only_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Modal/vLLM baselines are usually text-only; keep the incident context usable."""
    normalized: list[dict[str, Any]] = []
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                if part.get("type") == "text":
                    parts.append(part.get("text", ""))
                elif part.get("type") == "image_url":
                    parts.append("[Pipeline snapshot image attached in the Cerebras run; use the alert text and tools here.]")
            normalized.append({**msg, "content": "\n".join(p for p in parts if p)})
        else:
            normalized.append(msg)
    return normalized


_TEXT_TOOL_RE = re.compile(
    r"<\|tool_call\>\s*call:(?P<path>[A-Za-z_][\w:.-]*)\s*(?P<args>\{.*?\})\s*<tool_call\|>",
    re.DOTALL,
)

_TOOL_NAME_ALIASES = {
    "runbook_search": "query_runbook",
    "search_runbook": "query_runbook",
    "search_runbooks": "query_runbook",
    "query_runbooks": "query_runbook",
    "query_knowledge_base": "query_runbook",
    "similar_failures_search": "find_similar_failures",
    "search_similar_failures": "find_similar_failures",
    "find_similar_incidents": "find_similar_failures",
    "search_similar_incidents": "find_similar_failures",
    "get_recent_config_changes": "list_recent_config_changes",
    "get_config_diff": "config_diff",
    "get_logs": "get_job_logs",
    "get_task_logs": "get_job_logs",
}


def _tool_name(name: str) -> str:
    return _TOOL_NAME_ALIASES.get((name or "").strip(), (name or "").strip())


def _loads_tool_args(raw: str) -> dict[str, Any]:
    """Parse Gemma/vLLM's textual tool-call args, including `{query: "..."}`."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        fixed = re.sub(r"([{,]\s*)([A-Za-z_][\w-]*)\s*:", r'\1"\2":', raw)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            return {}


def _extract_text_tool_calls(content: str) -> tuple[str, list[ToolCall]]:
    """Convert Gemma text markers into OpenAI-style tool calls.

    Some vLLM/Gemma tool templates emit e.g.
    `<|tool_call>call:knowledge:query_runbook{query: "..."}<tool_call|>`
    as plain content instead of `message.tool_calls`. The incident agent expects
    structured tool calls, so normalize that here.
    """
    tool_calls: list[ToolCall] = []
    for match in _TEXT_TOOL_RE.finditer(content or ""):
        name = _tool_name(match.group("path").split(":")[-1])
        tool_calls.append(_mk_toolcall(name, _loads_tool_args(match.group("args"))))
    cleaned = _TEXT_TOOL_RE.sub("", content or "").strip()
    return cleaned, tool_calls


class BaselineClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.simulated = not self.settings.has_baseline
        self.label = self.settings.baseline_label
        self.model = self.settings.baseline_model or "gpu-baseline"
        # Authoritative usage from the endpoint, populated after stream_tokens().
        self.last_usage: dict[str, Any] | None = None

    async def stream_tokens(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]:
        self.last_usage = None
        if self.simulated:
            n = 0
            async for chunk in self._simulated_stream():
                n += 1
                yield chunk
            self.last_usage = {"completion_tokens": n}
            return

        payload: dict[str, Any] = {
            "model": self.settings.baseline_model,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
            # vLLM extension: reason on the GPU too, so both engines run the *same*
            # Gemma 4 workload (chain-of-thought + answer) - a fair, like-for-like
            # race. Flip to False if you want the GPU to skip thinking.
            "chat_template_kwargs": {"enable_thinking": True},
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        url = f"{self.settings.baseline_base_url.rstrip('/')}/chat/completions"
        headers = {}
        if self.settings.baseline_api_key:
            headers["Authorization"] = f"Bearer {self.settings.baseline_api_key}"
        async with httpx.AsyncClient(timeout=180.0, follow_redirects=True) as client:
            attempts = [
                payload,
                {k: v for k, v in payload.items() if k != "chat_template_kwargs"},
                {k: v for k, v in payload.items()
                 if k not in {"chat_template_kwargs", "stream_options"}},
            ]
            last_error: httpx.HTTPStatusError | None = None
            for candidate in attempts:
                try:
                    async with client.stream("POST", url, json=candidate, headers=headers) as r:
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
                            # vLLM emits reasoning under `reasoning_content` (with the gemma4
                            # reasoning parser) and the answer under `content` - surface both.
                            d = choices[0].get("delta") or {}
                            delta = (d.get("content") or d.get("reasoning_content")
                                     or d.get("reasoning"))
                            if delta:
                                yield delta
                    return
                except httpx.HTTPStatusError as exc:
                    # Managed OpenAI-compatible endpoints may reject vLLM-specific
                    # fields. Retry without them before surfacing the error.
                    if exc.response.status_code not in (400, 422):
                        raise
                    last_error = exc
                    continue
            if last_error:
                raise last_error

    async def _simulated_stream(self) -> AsyncGenerator[str, None]:
        text = (
            "Root cause: config change chg_8f2a1c cut transform worker memory from "
            "8192MB to 2048MB, so the transform task was OOMKilled. Recommended fix: "
            "revert the change to restore 8192MB and rerun the nightly ETL; the failure "
            "is deterministic so a plain rerun would fail again."
        )
        tps = max(5.0, self.settings.baseline_sim_tps)
        for word in text.split(" "):
            yield word + " "
            await asyncio.sleep(1.0 / tps)

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        reasoning_effort: str | None = None,
        step: str | None = None,
        json_object: bool = False,
    ) -> ChatResult:
        """Incident-compatible non-streaming chat call for the Modal/GPU race."""
        if self.simulated:
            await asyncio.sleep(0.35)
            res = _simulated_completion(step, json_object)
            res.model = f"{self.model} (sim)"
            res.simulated = True
            return res

        payload: dict[str, Any] = {
            "model": self.settings.baseline_model,
            "messages": _text_only_messages(messages),
            "chat_template_kwargs": {"enable_thinking": bool(reasoning_effort)},
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if json_object:
            payload["response_format"] = {"type": "json_object"}

        url = f"{self.settings.baseline_base_url.rstrip('/')}/chat/completions"
        headers = {}
        if self.settings.baseline_api_key:
            headers["Authorization"] = f"Bearer {self.settings.baseline_api_key}"

        attempts = [
            payload,
            {k: v for k, v in payload.items() if k != "chat_template_kwargs"},
            {k: v for k, v in payload.items() if k not in {"chat_template_kwargs", "response_format"}},
            {k: v for k, v in payload.items()
             if k not in {"chat_template_kwargs", "response_format", "tools", "tool_choice"}},
        ]
        last_error: httpx.HTTPStatusError | None = None
        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=180.0, follow_redirects=True) as client:
            for candidate in attempts:
                try:
                    r = await client.post(url, json=candidate, headers=headers)
                    r.raise_for_status()
                    data = r.json()
                    break
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code not in (400, 422):
                        raise
                    last_error = exc
                    continue
            else:
                if last_error:
                    raise last_error
                raise RuntimeError("Modal baseline returned no response")

        latency = (time.perf_counter() - t0) * 1000.0
        choice = (data.get("choices") or [{}])[0].get("message") or {}
        content = choice.get("content") or choice.get("reasoning_content") or ""
        tool_calls: list[ToolCall] = []
        for tc in choice.get("tool_calls") or []:
            fn = tc.get("function", {})
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(ToolCall(id=tc.get("id", _mk_toolcall(fn.get("name", ""), {}).id),
                                       name=_tool_name(fn.get("name", "")), arguments=args))
        cleaned_content, text_tool_calls = _extract_text_tool_calls(content)
        if text_tool_calls:
            content = cleaned_content
            tool_calls.extend(text_tool_calls)
        usage = data.get("usage", {})
        self.last_usage = usage or None
        return ChatResult(
            content=content,
            tool_calls=tool_calls,
            latency_ms=latency,
            completion_tokens=int(usage.get("completion_tokens", 0) or max(1, len(content) // 4)),
            model=data.get("model", self.model),
            simulated=False,
        )
