"""Incident endpoints: alert webhook (auto-start), manual start, SSE stream."""
from __future__ import annotations

import asyncio
import json

import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from app.agents.schemas import IncidentTrigger
from app.audit import audit_log
from app.incident_service import get_service
from app.pipeline.adapter import get_adapter
from app.pipeline.scenarios import get_scenario, list_scenarios

router = APIRouter(prefix="/api/incidents", tags=["incidents"])


def _trigger_for_scenario(scenario_id: str | None, source: str) -> IncidentTrigger:
    s = get_scenario(scenario_id)
    return IncidentTrigger(
        source=source, title=s.title, job_id=s.job_id, failed_task=s.failed_task,
        summary=s.summary, scenario_id=s.id,
    )


@router.get("/scenarios")
async def scenarios():
    """The library of investigable incident packs (for the scenario picker)."""
    return {"scenarios": list_scenarios()}


@router.get("/snapshot.png")
async def snapshot_png(scenario_id: str | None = None):
    """The DAG/build snapshot the alert carries (read by Gemma 4 vision)."""
    if scenario_id:
        path = get_scenario(scenario_id).snapshot_path
        try:
            from app.pipeline.gen_snapshot import generate_snapshot

            if not os.path.exists(path):
                generate_snapshot(path, get_scenario(scenario_id).snapshot)
        except Exception:
            pass
    else:
        path = get_adapter().get_dag_snapshot_path()
    if not os.path.exists(path):
        raise HTTPException(404, "snapshot not generated")
    return FileResponse(path, media_type="image/png")


@router.post("/webhook")
async def alert_webhook(trigger: IncidentTrigger | None = None):
    """Job-failed alert webhook. Auto-starts the investigation with no human."""
    svc = get_service()
    if trigger is None:
        trig = _trigger_for_scenario(None, "webhook")
    else:
        trig = trigger
        if not (trigger.title and trigger.job_id and trigger.failed_task):
            trig = _trigger_for_scenario(trigger.scenario_id, "webhook")
    trig.source = "webhook"
    incident = svc.open_incident(trig)
    svc.start_investigation(incident)
    return {"incident_id": incident.id, "status": incident.status.value}


@router.post("/start")
async def manual_start(trigger: IncidentTrigger):
    """Manual start (engineer-initiated), optionally with an attached screenshot."""
    svc = get_service()
    # If a scenario is chosen without a custom screenshot, align the trigger
    # metadata to that scenario so the agent investigates the matching world.
    if trigger.scenario_id and not trigger.snapshot_data_uri:
        s = get_scenario(trigger.scenario_id)
        trigger.title, trigger.job_id = s.title, s.job_id
        trigger.failed_task, trigger.summary = s.failed_task, s.summary
    trigger.source = "manual"
    incident = svc.open_incident(trigger)
    svc.start_investigation(incident)
    return {"incident_id": incident.id, "status": incident.status.value}


@router.get("/{incident_id}")
async def get_incident(incident_id: str):
    incident = get_service().get(incident_id)
    if incident is None:
        raise HTTPException(404, "incident not found")
    return incident.model_dump()


@router.get("/{incident_id}/audit")
async def get_audit(incident_id: str):
    return {"entries": audit_log.read_for_incident(incident_id)}


@router.get("/{incident_id}/stream")
async def stream(incident_id: str):
    svc = get_service()
    incident = svc.get(incident_id)
    if incident is None:
        raise HTTPException(404, "incident not found")

    async def event_gen():
        # Replay events already produced (so late subscribers catch up).
        for ev in list(incident.events):
            yield f"data: {ev.model_dump_json()}\n\n"
        q = svc.subscribe(incident_id)
        try:
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"data: {ev.model_dump_json()}\n\n"
                    if ev.type == "done":
                        break
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            svc.unsubscribe(incident_id, q)

    return StreamingResponse(event_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
