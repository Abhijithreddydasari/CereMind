"""Back-compat shim.

The single hardcoded incident was generalized into app.pipeline.scenarios. This
module re-exports the default (OOM) scenario's constants so older imports keep
working (smoke_cerebras, gen_snapshot __main__, airflow_backend).
"""
from __future__ import annotations

from app.pipeline.scenarios import DEFAULT_SCENARIO_ID, get_scenario

_OOM = get_scenario(DEFAULT_SCENARIO_ID)

JOB_ID = _OOM.job_id
DAG = list(_OOM.dag)
CULPRIT_CHANGE_ID = _OOM.culprit_change_id
SNAPSHOT_PATH = _OOM.snapshot_path
GOOD_MEMORY_MB = 8192
BAD_MEMORY_MB = 2048
