"""Real Cerebras smoke test (requires CEREBRAS_API_KEY in .env or env).

Verifies the three Gemma-4-on-Cerebras capabilities CereMind relies on:
  1. plain chat completion
  2. strict tool calling (constrained decoding) composed with reasoning_effort
  3. image input (vision) via Chat Completions

Run: python smoke_cerebras.py
"""
from __future__ import annotations

import asyncio
import base64
import os
import sys

from app.config import get_settings
from app.llm.cerebras_client import CerebrasClient
from app.pipeline.seed import SNAPSHOT_PATH


async def main() -> int:
    s = get_settings()
    if not s.has_cerebras:
        print("CEREBRAS_API_KEY not set - skipping real smoke test.")
        print("Set it in .env to verify the live Cerebras path.")
        return 0

    client = CerebrasClient()
    print(f"model = {client.model}")

    print("\n[1] plain chat ...")
    r = await client.chat_completion(
        messages=[{"role": "user", "content": "Reply with the single word: ready"}],
        reasoning_effort="low",
    )
    print(f"    -> {r.content!r}  ({r.latency_ms:.0f} ms, {r.completion_tokens} tok)")

    print("\n[2] strict tool call + reasoning_effort ...")
    tools = [{
        "type": "function",
        "function": {
            "name": "get_job_logs",
            "description": "Fetch logs for a failed run.",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {"run_id": {"type": "string"}},
                "required": ["run_id"],
                "additionalProperties": False,
            },
        },
    }]
    r2 = await client.chat_completion(
        messages=[{"role": "user", "content": "Get the logs for run_2004 using your tool."}],
        tools=tools, reasoning_effort="medium",
    )
    if r2.tool_calls:
        tc = r2.tool_calls[0]
        print(f"    -> tool_call {tc.name}({tc.arguments})  ({r2.latency_ms:.0f} ms)")
    else:
        print(f"    -> no tool call; content={r2.content!r}")

    print("\n[3] vision (image input) ...")
    if os.path.exists(SNAPSHOT_PATH):
        with open(SNAPSHOT_PATH, "rb") as f:
            uri = "data:image/png;base64," + base64.b64encode(f.read()).decode()
        r3 = await client.chat_completion(messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": "Which pipeline stage failed in this snapshot?"},
                {"type": "image_url", "image_url": {"url": uri}},
            ],
        }], reasoning_effort="low")
        print(f"    -> {r3.content[:160]!r}  ({r3.latency_ms:.0f} ms)")
    else:
        print("    snapshot missing; run gen_snapshot first.")

    print("\nReal Cerebras smoke test complete.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
