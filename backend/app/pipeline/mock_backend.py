"""Seeded, deterministic mock of the 'AcmeShop nightly ETL' pipeline.

DAG: ingest -> transform -> load. A config change ~1h ago cut worker memory
8192MB -> 2048MB, so the `transform` task is OOMKilled. The fix is to revert
that config (or retry with more memory) and rerun; only then does the run go
green. Rerunning without fixing config fails again (the failure is NOT
transient), which is what makes the agent's diagnosis meaningful.
"""
from __future__ import annotations

import threading
import time
from typing import Any

from app.pipeline.seed import (
    CULPRIT_CHANGE_ID,
    GOOD_MEMORY_MB,
    BAD_MEMORY_MB,
    build_seed,
)


class MockBackend:
    _singleton: "MockBackend | None" = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self.name = "mock"
        self.reset()

    # Singleton so API + agent share one mutable world per process.
    @classmethod
    def instance(cls) -> "MockBackend":
        with cls._lock:
            if cls._singleton is None:
                cls._singleton = cls()
            return cls._singleton

    def reset(self) -> None:
        seed = build_seed()
        self.job_id: str = seed["job_id"]
        self.dag: list[str] = seed["dag"]
        self.runs: list[dict[str, Any]] = seed["runs"]
        self.logs: dict[str, dict[str, str]] = seed["logs"]
        self.config_changes: list[dict[str, Any]] = seed["config_changes"]
        # Current effective worker memory (the injected fault is the low value).
        self.current_memory_mb: int = BAD_MEMORY_MB
        self.reverted_changes: set[str] = set()
        self.snapshot_path: str = seed["snapshot_path"]

    # --- read tools ---------------------------------------------------------
    def get_job_runs(self, job_id: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        runs = [r for r in self.runs if job_id in (None, r["job_id"])]
        return runs[-limit:][::-1]

    def get_job_logs(self, run_id: str | None = None, task_id: str | None = None) -> dict[str, Any]:
        # Default to the latest failed run.
        if run_id is None:
            failed = [r for r in self.runs if r["status"] == "failed"]
            run_id = (failed or self.runs)[-1]["run_id"]
        run_logs = self.logs.get(run_id, {})
        if task_id:
            return {"run_id": run_id, "task_id": task_id, "log": run_logs.get(task_id, "")}
        return {"run_id": run_id, "tasks": run_logs}

    def get_metrics(self, task_id: str | None = None, metric: str = "memory_mb") -> dict[str, Any]:
        task_id = task_id or "transform"
        # Memory climbs and hits the (lowered) limit -> OOM.
        limit = self.current_memory_mb
        points = []
        base = limit * 0.35
        for i in range(12):
            val = base + (limit * 0.95 - base) * (i / 11)
            # When the limit is low, it pegs at the limit (OOM) near the end.
            if val >= limit * 0.98 and limit <= BAD_MEMORY_MB:
                val = limit
            points.append({"t": i * 10, f"{metric}": round(val, 1)})
        return {
            "task_id": task_id,
            "metric": metric,
            "limit": limit,
            "unit": "MB",
            "oom": limit <= BAD_MEMORY_MB,
            "points": points,
        }

    def list_recent_config_changes(self, limit: int = 10) -> list[dict[str, Any]]:
        out = []
        for c in self.config_changes[-limit:][::-1]:
            cc = dict(c)
            cc["reverted"] = c["id"] in self.reverted_changes
            out.append(cc)
        return out

    def config_diff(self, change_id: str) -> dict[str, Any]:
        for c in self.config_changes:
            if c["id"] == change_id:
                return {
                    "id": c["id"],
                    "author": c["author"],
                    "ts": c["ts"],
                    "summary": c["summary"],
                    "diff": c["diff"],
                    "reverted": c["id"] in self.reverted_changes,
                }
        return {"error": f"unknown change_id {change_id}"}

    def get_dag_snapshot_path(self) -> str:
        return self.snapshot_path

    # --- remediation (mutating) --------------------------------------------
    def revert_config(self, change_id: str) -> dict[str, Any]:
        if change_id != CULPRIT_CHANGE_ID:
            return {
                "ok": False,
                "change_id": change_id,
                "message": "Change reverted, but it was not the cause of the failure.",
            }
        self.reverted_changes.add(change_id)
        self.current_memory_mb = GOOD_MEMORY_MB
        return {
            "ok": True,
            "change_id": change_id,
            "message": f"Reverted {change_id}: worker memory restored to {GOOD_MEMORY_MB}MB.",
            "worker_memory_mb": GOOD_MEMORY_MB,
        }

    def retry_with_params(self, job_id: str, params: dict[str, Any]) -> dict[str, Any]:
        mem = params.get("worker_memory_mb") or params.get("memory_mb")
        if mem and int(mem) >= GOOD_MEMORY_MB:
            self.current_memory_mb = int(mem)
            return {
                "ok": True,
                "job_id": job_id,
                "message": f"Applied override worker_memory_mb={mem} for next run.",
                "worker_memory_mb": int(mem),
            }
        return {
            "ok": False,
            "job_id": job_id,
            "message": "Param override insufficient; transform needs >= "
            f"{GOOD_MEMORY_MB}MB to avoid OOM.",
        }

    def rerun_job(self, job_id: str) -> dict[str, Any]:
        healthy = self.current_memory_mb >= GOOD_MEMORY_MB
        status = "success" if healthy else "failed"
        run_id = f"run_{int(time.time())}"
        new_run = {
            "run_id": run_id,
            "job_id": job_id,
            "status": status,
            "started_at": time.time(),
            "duration_s": 142 if healthy else 38,
            "failed_task": None if healthy else "transform",
            "trigger": "rerun",
        }
        self.runs.append(new_run)
        if not healthy:
            self.logs[run_id] = {
                "ingest": "OK ingested 1,240,338 rows",
                "transform": "ERROR: transform OOMKilled (memory limit "
                f"{self.current_memory_mb}MB exceeded). Process killed by cgroup.",
            }
        else:
            self.logs[run_id] = {
                "ingest": "OK ingested 1,240,338 rows",
                "transform": "OK transformed 1,240,338 rows (peak mem 6,912MB)",
                "load": "OK loaded 1,240,338 rows into warehouse.checkout_facts",
            }
        return {
            "ok": healthy,
            "run_id": run_id,
            "status": status,
            "message": "Rerun succeeded; pipeline is green."
            if healthy
            else "Rerun failed again (transform OOMKilled). Root cause not yet fixed.",
        }
