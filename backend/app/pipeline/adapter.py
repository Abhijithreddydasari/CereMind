"""PipelineAdapter: the interface the agent investigates and acts on.

Two backends implement this: `mock` (seeded, deterministic, default) and
`airflow` (optional, local docker-compose Airflow via REST). The agent logic is
identical across backends; only the adapter changes. This is the seam that makes
CereMind deployable against a real orchestrator in production.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class PipelineAdapter(ABC):
    name: str = "base"

    # --- read tools ---------------------------------------------------------
    @abstractmethod
    def get_job_runs(self, job_id: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def get_job_logs(self, run_id: str | None = None, task_id: str | None = None) -> dict[str, Any]:
        ...

    @abstractmethod
    def get_metrics(self, task_id: str | None = None, metric: str = "memory_mb") -> dict[str, Any]:
        ...

    @abstractmethod
    def list_recent_config_changes(self, limit: int = 10) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def config_diff(self, change_id: str) -> dict[str, Any]:
        ...

    @abstractmethod
    def get_dag_snapshot_path(self) -> str:
        """Path to a rendered DAG/build-status PNG for the vision step."""
        ...

    # --- remediation (mutating) --------------------------------------------
    @abstractmethod
    def revert_config(self, change_id: str) -> dict[str, Any]:
        ...

    @abstractmethod
    def retry_with_params(self, job_id: str, params: dict[str, Any]) -> dict[str, Any]:
        ...

    @abstractmethod
    def rerun_job(self, job_id: str) -> dict[str, Any]:
        ...


def get_adapter() -> PipelineAdapter:
    """Factory honoring PIPELINE_BACKEND."""
    from app.config import get_settings

    settings = get_settings()
    if settings.pipeline_backend == "airflow":
        try:
            from app.pipeline.airflow_backend import AirflowBackend

            return AirflowBackend()
        except Exception:
            # Fall back to mock so the app always boots.
            pass
    from app.pipeline.mock_backend import MockBackend

    return MockBackend.instance()
