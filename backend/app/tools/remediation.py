"""Remediation tools (mutating). Gated by risk tier + human approval."""
from __future__ import annotations

from typing import Any

from app.pipeline.adapter import get_adapter


def revert_config(change_id: str) -> dict[str, Any]:
    return get_adapter().revert_config(change_id=change_id)


def retry_with_params(job_id: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return get_adapter().retry_with_params(job_id=job_id, params=params or {})


def rerun_job(job_id: str) -> dict[str, Any]:
    return get_adapter().rerun_job(job_id=job_id)


def create_ticket(title: str, body: str = "") -> dict[str, Any]:
    return {"ok": True, "ticket_id": "JIRA-4821", "title": title}


def post_to_slack(channel: str = "#incidents", message: str = "") -> dict[str, Any]:
    return {"ok": True, "channel": channel, "message": message}
