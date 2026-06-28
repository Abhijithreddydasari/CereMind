"""Specialist sub-agents (telemetry / change / knowledge).

Each specialist is a bounded ReAct loop with ONLY its own tools. It calls tools,
observes results, and returns a short finding. Events are yielded so the war-room
console can render the live, audited reasoning trail.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator

from app.agents.prompts import SPECIALIST_SYSTEM
from app.agents.schemas import AgentEvent
from app.llm.cerebras_client import CerebrasClient
from app.tools import registry

MAX_ROUNDS = 3


@dataclass
class SpecialistResult:
    specialist: str
    finding: str = ""
    observations: list[dict[str, Any]] = field(default_factory=list)


def _truncate(obj: Any, n: int = 600) -> str:
    s = json.dumps(obj, default=str)
    return s if len(s) <= n else s[:n] + "...(truncated)"


async def run_specialist(
    client: CerebrasClient,
    incident_id: str,
    specialist: str,
    context: str,
) -> AsyncGenerator[tuple[AgentEvent, SpecialistResult | None], None]:
    """Yield (event, result-or-None). The final yield carries the SpecialistResult."""
    result = SpecialistResult(specialist=specialist)
    tools = registry.SPECIALIST_TOOLS[specialist]

    yield AgentEvent(incident_id=incident_id, type="specialist_start", actor=specialist,
                     title=f"{specialist.capitalize()} specialist engaged"), None

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SPECIALIST_SYSTEM[specialist]},
        {"role": "user", "content": context},
    ]

    finding = ""
    for rnd in range(MAX_ROUNDS):
        step = f"{specialist}:act" if rnd == 0 else f"{specialist}:summary"
        res = await client.chat_completion(
            messages=messages, tools=tools, reasoning_effort="low", step=step,
        )
        if res.content and not res.tool_calls:
            finding = res.content
            break
        if res.content:
            yield AgentEvent(incident_id=incident_id, type="thought", actor=specialist,
                             detail=res.content), None

        if res.tool_calls:
            messages.append({
                "role": "assistant",
                "content": res.content or None,
                "tool_calls": [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)}}
                    for tc in res.tool_calls
                ],
            })
            for tc in res.tool_calls:
                tier = registry.risk_tier(tc.name)
                yield AgentEvent(
                    incident_id=incident_id, type="tool_call", actor=specialist,
                    title=tc.name, detail=_truncate(tc.arguments, 240),
                    data={"tool": tc.name, "args": tc.arguments, "risk_tier": tier},
                ), None
                obs = registry.dispatch(tc.name, tc.arguments)
                result.observations.append({"tool": tc.name, "args": tc.arguments, "result": obs})
                messages.append({"role": "tool", "tool_call_id": tc.id,
                                 "content": _truncate(obs, 1200)})
                yield AgentEvent(
                    incident_id=incident_id, type="observation", actor=specialist,
                    title=f"{tc.name} -> result", detail=_truncate(obs, 360),
                    data={"tool": tc.name, "result": obs},
                ), None
        else:
            finding = res.content
            break

    result.finding = finding or "(no finding)"
    yield AgentEvent(incident_id=incident_id, type="specialist_done", actor=specialist,
                     title=f"{specialist.capitalize()} finding", detail=result.finding), result
