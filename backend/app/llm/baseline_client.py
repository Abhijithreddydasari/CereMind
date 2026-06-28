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

    async def stream_tokens(self, messages: list[dict[str, Any]]) -> AsyncGenerator[str, None]:
        if self.simulated:
            async for chunk in self._simulated_stream():
                yield chunk
            return

        payload = {"model": self.settings.baseline_model, "messages": messages, "stream": True}
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
                        delta = obj["choices"][0]["delta"].get("content")
                        if delta:
                            yield delta
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

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
