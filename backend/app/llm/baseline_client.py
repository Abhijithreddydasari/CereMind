"""GPU baseline client for the side-by-side speed comparison.

Streams from any OpenAI-compatible endpoint when configured; otherwise simulates
a representative GPU token rate so the comparison still renders. The UI always
labels this pane as a representative baseline to stay honest.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncGenerator

import httpx

from app.config import get_settings


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
        async with httpx.AsyncClient(timeout=180.0) as client:
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
                    # vLLM emits reasoning under `reasoning_content` (with the gemma4
                    # reasoning parser) and the answer under `content` - surface both.
                    d = choices[0].get("delta") or {}
                    delta = d.get("content") or d.get("reasoning_content") or d.get("reasoning")
                    if delta:
                        yield delta

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
