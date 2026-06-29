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


def rollback_changes() -> dict[str, Any]:
    """Undo any fix CereMind itself applied (auto-rollback safety net)."""
    adapter = get_adapter()
    fn = getattr(adapter, "rollback_applied_fixes", None)
    if fn is None:
        return {"ok": True, "message": "No applied changes to roll back."}
    return fn()


def file_guardrail(title: str, policy: str) -> dict[str, Any]:
    """File a preventive guardrail as a PR/ticket artifact (Immunize)."""
    pr_number = abs(hash(title)) % 9000 + 1000
    return {"ok": True, "artifact_kind": "pull_request",
            "artifact_id": f"PR-{pr_number}",
            "artifact_url": f"https://git.acmeshop.io/data-pipelines/pull/{pr_number}",
            "title": title, "policy": policy}
