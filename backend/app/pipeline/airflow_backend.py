"""Optional Airflow backend (production seam, stretch goal).

Maps the PipelineAdapter onto Apache Airflow's stable REST API. Intended for a
local docker-compose Airflow, NOT Cloud Composer. This is a thin, best-effort
implementation: it demonstrates that swapping the investigated system is purely
an adapter change. Falls back to the mock backend on any error (see
adapter.get_adapter).
"""
from __future__ import annotations

from typing import Any

import httpx

from app.config import get_settings
from app.pipeline.adapter import PipelineAdapter


class AirflowBackend(PipelineAdapter):
    name = "airflow"

    def __init__(self) -> None:
        s = get_settings()
        self.base = s.airflow_base_url.rstrip("/")
        self.auth = (s.airflow_username, s.airflow_password)
        # Fail fast so the factory can fall back to mock if Airflow is down.
        self._client = httpx.Client(auth=self.auth, timeout=5.0)
        self._client.get(f"{self.base}/health")

    def _get(self, path: str, **params: Any) -> dict[str, Any]:
        r = self._client.get(f"{self.base}{path}", params=params)
        r.raise_for_status()
        return r.json()

    def get_job_runs(self, job_id: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        dag_id = job_id or "acmeshop_nightly_etl"
        data = self._get(f"/dags/{dag_id}/dagRuns", order_by="-start_date", limit=limit)
        return [
            {
                "run_id": r["dag_run_id"],
                "job_id": dag_id,
                "status": "success" if r["state"] == "success" else "failed"
                if r["state"] == "failed" else r["state"],
                "started_at": r.get("start_date"),
                "trigger": r.get("run_type"),
            }
            for r in data.get("dag_runs", [])
        ]

    def get_job_logs(self, run_id: str | None = None, task_id: str | None = None) -> dict[str, Any]:
        dag_id = "acmeshop_nightly_etl"
        task_id = task_id or "transform"
        data = self._client.get(
            f"{self.base}/dags/{dag_id}/dagRuns/{run_id}/taskInstances/{task_id}/logs/1"
        )
        return {"run_id": run_id, "task_id": task_id, "log": data.text}

    def get_metrics(self, task_id: str | None = None, metric: str = "memory_mb") -> dict[str, Any]:
        # Airflow does not expose worker memory series natively; surface a note.
        return {"task_id": task_id, "metric": metric, "points": [],
                "note": "Connect Prometheus for memory series in production."}

    def list_recent_config_changes(self, limit: int = 10) -> list[dict[str, Any]]:
        # In production this maps to a git/CI change feed.
        return []

    def config_diff(self, change_id: str) -> dict[str, Any]:
        return {"id": change_id, "note": "Wire to git provider in production."}

    def get_dag_snapshot_path(self) -> str:
        from app.pipeline.seed import SNAPSHOT_PATH

        return SNAPSHOT_PATH

    def revert_config(self, change_id: str) -> dict[str, Any]:
        return {"ok": False, "note": "Wire to git revert + redeploy in production."}

    def retry_with_params(self, job_id: str, params: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "note": f"Would set conf={params} on next trigger."}

    def rerun_job(self, job_id: str) -> dict[str, Any]:
        r = self._client.post(f"{self.base}/dags/{job_id}/dagRuns", json={})
        return {"ok": r.status_code < 300, "status_code": r.status_code}
