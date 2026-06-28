"""Deterministic seed data for the AcmeShop nightly ETL pipeline."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

JOB_ID = "acmeshop_nightly_etl"
DAG = ["ingest", "transform", "load"]

GOOD_MEMORY_MB = 8192
BAD_MEMORY_MB = 2048

CULPRIT_CHANGE_ID = "chg_8f2a1c"

DATA_DIR = Path(__file__).resolve().parent / "data"
SNAPSHOT_PATH = str(DATA_DIR / "dag_snapshot.png")

# Fixed reference time so the demo reads consistently.
_T0 = 1_751_000_000  # arbitrary fixed epoch


def _ago(seconds: int) -> float:
    return _T0 - seconds


def build_seed() -> dict[str, Any]:
    runs: list[dict[str, Any]] = [
        {
            "run_id": "run_2001",
            "job_id": JOB_ID,
            "status": "success",
            "started_at": _ago(3 * 86400),
            "duration_s": 139,
            "failed_task": None,
            "trigger": "schedule",
        },
        {
            "run_id": "run_2002",
            "job_id": JOB_ID,
            "status": "success",
            "started_at": _ago(2 * 86400),
            "duration_s": 144,
            "failed_task": None,
            "trigger": "schedule",
        },
        {
            "run_id": "run_2003",
            "job_id": JOB_ID,
            "status": "success",
            "started_at": _ago(1 * 86400),
            "duration_s": 141,
            "failed_task": None,
            "trigger": "schedule",
        },
        {
            # The failure under investigation.
            "run_id": "run_2004",
            "job_id": JOB_ID,
            "status": "failed",
            "started_at": _ago(600),
            "duration_s": 37,
            "failed_task": "transform",
            "trigger": "schedule",
        },
    ]

    logs: dict[str, dict[str, str]] = {
        "run_2003": {
            "ingest": "OK ingested 1,233,901 rows in 41s",
            "transform": "OK transformed 1,233,901 rows (peak mem 6,840MB) in 78s",
            "load": "OK loaded 1,233,901 rows into warehouse.checkout_facts",
        },
        "run_2004": {
            "ingest": "OK ingested 1,240,338 rows in 42s",
            "transform": (
                "INFO starting transform stage (worker_memory_limit=2048MB)\n"
                "INFO loading dataframe partitions...\n"
                "WARN memory usage 1,910MB / 2,048MB\n"
                "ERROR transform OOMKilled: memory limit 2048MB exceeded. "
                "Process killed by cgroup (signal 9).\n"
                "ERROR task 'transform' failed; downstream 'load' skipped."
            ),
            "load": "SKIPPED (upstream transform failed)",
        },
    }

    config_changes: list[dict[str, Any]] = [
        {
            "id": "chg_4b91de",
            "author": "maria@acmeshop.io",
            "ts": _ago(9 * 86400),
            "summary": "Add retry policy to load task",
            "diff": "+ load.retries: 3\n+ load.retry_delay: 60s",
        },
        {
            "id": "chg_7c30aa",
            "author": "deploybot",
            "ts": _ago(5 * 86400),
            "summary": "Bump base image to python:3.11-slim",
            "diff": "- image: python:3.10-slim\n+ image: python:3.11-slim",
        },
        {
            # The culprit: cost-saving change that cut transform memory.
            "id": CULPRIT_CHANGE_ID,
            "author": "costopt-bot",
            "ts": _ago(3600),
            "summary": "Reduce worker memory to cut cloud spend",
            "diff": (
                "  transform:\n"
                f"-   worker_memory_mb: {GOOD_MEMORY_MB}\n"
                f"+   worker_memory_mb: {BAD_MEMORY_MB}"
            ),
        },
    ]

    if not os.path.exists(SNAPSHOT_PATH):
        try:
            from app.pipeline.gen_snapshot import generate_snapshot

            generate_snapshot(SNAPSHOT_PATH)
        except Exception:
            # Vision step degrades gracefully if matplotlib is unavailable.
            pass

    return {
        "job_id": JOB_ID,
        "dag": DAG,
        "runs": runs,
        "logs": logs,
        "config_changes": config_changes,
        "snapshot_path": SNAPSHOT_PATH,
    }
