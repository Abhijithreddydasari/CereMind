"""Telemetry specialist tools: job runs, logs, metrics."""
from __future__ import annotations

from typing import Any

from app.pipeline.adapter import get_adapter


def get_job_runs(job_id: str | None = None, limit: int = 5) -> dict[str, Any]:
    return {"runs": get_adapter().get_job_runs(job_id=job_id, limit=limit)}


def get_job_logs(run_id: str | None = None, task_id: str | None = None) -> dict[str, Any]:
    return get_adapter().get_job_logs(run_id=run_id, task_id=task_id)


def get_metrics(task_id: str | None = None, metric: str = "memory_mb") -> dict[str, Any]:
    return get_adapter().get_metrics(task_id=task_id, metric=metric)
