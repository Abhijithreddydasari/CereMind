"""In-memory incident store + SSE pub/sub + background run management."""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from app.agents.commander import Commander
from app.agents.schemas import AgentEvent, Incident, IncidentStatus, IncidentTrigger
from app.audit import audit_log


class IncidentService:
    def __init__(self) -> None:
        self._incidents: dict[str, Incident] = {}
        self._subscribers: dict[str, list[asyncio.Queue]] = {}
        self._commander = Commander()

    # --- store --------------------------------------------------------------
    def get(self, incident_id: str) -> Incident | None:
        return self._incidents.get(incident_id)

    def list(self) -> list[Incident]:
        return list(self._incidents.values())

    # --- pub/sub ------------------------------------------------------------
    def subscribe(self, incident_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.setdefault(incident_id, []).append(q)
        return q

    def unsubscribe(self, incident_id: str, q: asyncio.Queue) -> None:
        subs = self._subscribers.get(incident_id, [])
        if q in subs:
            subs.remove(q)

    async def _publish(self, incident: Incident, event: AgentEvent) -> None:
        incident.events.append(event)
        audit_log.record(incident.id, event.type,
                         {"actor": event.actor, "title": event.title, "detail": event.detail,
                          "data": event.data})
        for q in list(self._subscribers.get(incident.id, [])):
            await q.put(event)

    async def _drain(self, incident: Incident, gen: AsyncGenerator[AgentEvent, None]) -> None:
        try:
            async for event in gen:
                await self._publish(incident, event)
        except Exception as e:  # noqa: BLE001
            err = AgentEvent(incident_id=incident.id, type="error", actor="system",
                             title="Investigation error", detail=str(e))
            incident.status = IncidentStatus.FAILED
            await self._publish(incident, err)

    # --- lifecycle ----------------------------------------------------------
    def open_incident(self, trigger: IncidentTrigger) -> Incident:
        # Activate the selected incident pack in the (mock) backend so the agent
        # investigates the right world. No-op for non-mock backends.
        try:
            from app.pipeline.mock_backend import MockBackend

            MockBackend.instance().load_scenario(trigger.scenario_id)
        except Exception:
            pass
        incident = Incident(trigger=trigger)
        self._incidents[incident.id] = incident
        return incident

    def start_investigation(self, incident: Incident) -> None:
        gen = self._commander.investigate(incident)
        asyncio.create_task(self._drain(incident, gen))

    def approve(self, incident: Incident) -> None:
        gen = self._commander.remediate(incident)
        asyncio.create_task(self._drain(incident, gen))

    def reject(self, incident: Incident) -> None:
        gen = self._commander.reject(incident)
        asyncio.create_task(self._drain(incident, gen))


_service: IncidentService | None = None


def get_service() -> IncidentService:
    global _service
    if _service is None:
        _service = IncidentService()
    return _service
