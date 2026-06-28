"""Remediation approval gate endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.agents.schemas import IncidentStatus
from app.audit import audit_log
from app.incident_service import get_service

router = APIRouter(prefix="/api/incidents", tags=["actions"])


@router.post("/{incident_id}/approve")
async def approve(incident_id: str):
    svc = get_service()
    incident = svc.get(incident_id)
    if incident is None:
        raise HTTPException(404, "incident not found")
    if incident.status != IncidentStatus.AWAITING_APPROVAL:
        raise HTTPException(409, f"incident not awaiting approval (status={incident.status.value})")
    audit_log.record(incident_id, "approval", {"decision": "approved", "by": "operator"})
    svc.approve(incident)
    return {"ok": True, "status": "remediating"}


@router.post("/{incident_id}/reject")
async def reject(incident_id: str):
    svc = get_service()
    incident = svc.get(incident_id)
    if incident is None:
        raise HTTPException(404, "incident not found")
    if incident.status != IncidentStatus.AWAITING_APPROVAL:
        raise HTTPException(409, f"incident not awaiting approval (status={incident.status.value})")
    audit_log.record(incident_id, "approval", {"decision": "rejected", "by": "operator"})
    svc.reject(incident)
    return {"ok": True, "status": "rejected"}
