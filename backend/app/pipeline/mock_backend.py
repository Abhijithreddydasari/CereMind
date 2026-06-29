"""Seeded, deterministic mock of the investigated data/CI pipeline.

The backend is scenario-aware (see app.pipeline.scenarios): it loads one
incident "pack" at a time. Each pack injects a deterministic fault whose only
durable fix is to revert the culprit config change (one pack also accepts a
param override). Rerunning without the correct fix fails again - the failure is
NOT transient - which is what makes the agent's diagnosis meaningful.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Any, Optional

from app.pipeline.scenarios import (
    DEFAULT_SCENARIO_ID,
    Scenario,
    get_scenario,
)


class MockBackend:
    _singleton: "MockBackend | None" = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self.name = "mock"
        self.load_scenario(DEFAULT_SCENARIO_ID)

    # Singleton so API + agent share one mutable world per process.
    @classmethod
    def instance(cls) -> "MockBackend":
        with cls._lock:
            if cls._singleton is None:
                cls._singleton = cls()
            return cls._singleton

    # --- scenario lifecycle -------------------------------------------------
    def load_scenario(self, scenario_id: Optional[str]) -> Scenario:
        self.scenario = get_scenario(scenario_id)
        self.reset()
        return self.scenario

    def reset(self) -> None:
        s = self.scenario
        self.job_id = s.job_id
        self.dag = list(s.dag)
        self.runs = [dict(r) for r in s.runs]
        self.logs = {rid: dict(tasks) for rid, tasks in s.logs.items()}
        self.config_changes = [dict(c) for c in s.config_changes]
        self.reverted_changes: set[str] = set()
        self.applied_param_fix = False
        # Track what CereMind itself applied, so auto-rollback can undo it.
        self.applied_fixes: list[dict[str, Any]] = []
        # Test/demo affordance: force the first rerun to fail (exercises rollback).
        self.force_fail_rerun = False
        self._ensure_snapshot()

    def _ensure_snapshot(self) -> None:
        path = self.scenario.snapshot_path
        if not os.path.exists(path):
            try:
                from app.pipeline.gen_snapshot import generate_snapshot

                generate_snapshot(path, self.scenario.snapshot)
            except Exception:
                pass  # vision degrades gracefully if matplotlib is unavailable

    @property
    def is_fixed(self) -> bool:
        return (self.scenario.culprit_change_id in self.reverted_changes) or self.applied_param_fix

    # --- read tools ---------------------------------------------------------
    def get_job_runs(self, job_id: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        runs = [r for r in self.runs if job_id in (None, r["job_id"])]
        return runs[-limit:][::-1]

    def get_job_logs(self, run_id: str | None = None, task_id: str | None = None) -> dict[str, Any]:
        if run_id is None:
            failed = [r for r in self.runs if r["status"] == "failed"]
            run_id = (failed or self.runs)[-1]["run_id"]
        run_logs = self.logs.get(run_id, {})
        if task_id:
            return {"run_id": run_id, "task_id": task_id, "log": run_logs.get(task_id, "")}
        return {"run_id": run_id, "tasks": run_logs}

    def get_metrics(self, task_id: str | None = None, metric: str = "memory_mb") -> dict[str, Any]:
        m = dict(self.scenario.metrics)
        # Honor the requested task/metric labels while keeping the scenario's series.
        if task_id:
            m["task_id"] = task_id
        return m

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
                return {**{k: c[k] for k in ("id", "author", "ts", "summary", "diff")},
                        "reverted": c["id"] in self.reverted_changes}
        return {"error": f"unknown change_id {change_id}"}

    def get_dag_snapshot_path(self) -> str:
        self._ensure_snapshot()
        return self.scenario.snapshot_path

    # --- remediation (mutating) --------------------------------------------
    def revert_config(self, change_id: str) -> dict[str, Any]:
        if change_id != self.scenario.culprit_change_id:
            return {"ok": False, "change_id": change_id,
                    "message": "Change reverted, but it was not the cause of the failure."}
        self.reverted_changes.add(change_id)
        self.applied_fixes.append({"kind": "revert_config", "change_id": change_id})
        return {"ok": True, "change_id": change_id,
                "message": f"Reverted {change_id}: restored the pre-incident pipeline config."}

    def retry_with_params(self, job_id: str, params: dict[str, Any]) -> dict[str, Any]:
        pf = self.scenario.param_fix
        if pf:
            val = next((params.get(k) for k in pf["keys"] if params.get(k) is not None), None)
            if val is not None and int(val) >= int(pf["min"]):
                self.applied_param_fix = True
                self.applied_fixes.append({"kind": "param", "params": dict(params)})
                return {"ok": True, "job_id": job_id, "message": pf["message"]}
            return {"ok": False, "job_id": job_id,
                    "message": f"Param override insufficient; need >= {pf['min']} to fix."}
        return {"ok": False, "job_id": job_id,
                "message": "A param override does not address this failure class; revert the culprit change."}

    def rerun_job(self, job_id: str) -> dict[str, Any]:
        healthy = self.is_fixed and not self.force_fail_rerun
        status = "success" if healthy else "failed"
        run_id = f"run_{int(time.time() * 1000) % 1_000_000}"
        self.runs.append({
            "run_id": run_id, "job_id": job_id, "status": status,
            "started_at": time.time(),
            "duration_s": 142 if healthy else 24,
            "failed_task": None if healthy else self.scenario.failed_task,
            "trigger": "rerun",
        })
        self.logs[run_id] = dict(self.scenario.green_logs if healthy else self.scenario.red_logs)
        return {"ok": healthy, "run_id": run_id, "status": status,
                "message": ("Rerun succeeded; pipeline is green." if healthy
                            else f"Rerun failed again ({self.scenario.failed_task}). Root cause not yet fixed.")}

    # --- auto-rollback (undo CereMind's own change) ------------------------
    def rollback_applied_fixes(self) -> dict[str, Any]:
        undone: list[str] = []
        for fix in reversed(self.applied_fixes):
            if fix["kind"] == "revert_config":
                self.reverted_changes.discard(fix["change_id"])
                undone.append(f"re-applied {fix['change_id']} (undo of our revert)")
            elif fix["kind"] == "param":
                self.applied_param_fix = False
                undone.append("removed our param override")
        self.applied_fixes = []
        return {"ok": True, "undone": undone,
                "message": "Rolled back CereMind's changes; pipeline restored to pre-remediation state."}
