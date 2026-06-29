"""Multi-incident scenario engine.

Each scenario is a self-contained, deterministic incident "pack" for the
investigated data/CI pipeline. All four packs stay in CereMind's native
data/ETL/CI lane (deliberately distinct from generic web-service outages):

  1. oom_memory_cut   - a cost-cut config change lowered worker_memory_mb, so
                        the `transform` task is OOMKilled.
  2. schema_drift     - an upstream schema change renamed a column, so the
                        `transform` task fails a data-contract assertion.
  3. dependency_bump  - a base-image/library bump introduced an incompatible
                        API, so the `transform` task raises at import/call time.
  4. vendor_ratelimit - a concurrency bump made the `ingest` task hammer a
                        third-party API, which began returning HTTP 429.

A pack carries everything the agent observes (runs, logs, metrics, config
changes, a snapshot spec, RAG docs) plus the deterministic scripted-sim content
so the entire UX runs keyless. Each ends in a distinct fix and a distinct
preventive guardrail, so the agent's reasoning visibly differs per incident.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

DATA_DIR = Path(__file__).resolve().parent / "data"
# Drop a hand-made / ChatGPT-generated dashboard here as `<scenario_id>.png`
# (or .jpg/.webp) and it overrides the auto-generated snapshot for that scenario.
CUSTOM_DIR = DATA_DIR / "custom"
_CUSTOM_EXTS = (".png", ".jpg", ".jpeg", ".webp")

# Fixed reference epoch so every demo reads consistently.
_T0 = 1_751_000_000


def _ago(seconds: int) -> float:
    return _T0 - seconds


def _series(metric: str, limit: float, n: int = 12,
            start_frac: float = 0.35, end_frac: float = 0.99, peg: bool = True) -> list[dict[str, Any]]:
    pts: list[dict[str, Any]] = []
    lo, hi = limit * start_frac, limit * end_frac
    for i in range(n):
        val = lo + (hi - lo) * (i / (n - 1))
        if peg and val >= limit * 0.98:
            val = limit
        pts.append({"t": i * 10, metric: round(val, 1)})
    return pts


@dataclass
class Scenario:
    id: str
    title: str
    summary: str
    job_id: str
    dag: list[str]
    failed_task: str
    failed_run_id: str
    runs: list[dict[str, Any]]
    logs: dict[str, dict[str, str]]
    metrics: dict[str, Any]
    config_changes: list[dict[str, Any]]
    culprit_change_id: str
    cost_per_min: float          # business-impact: $/min of downtime
    green_logs: dict[str, str]   # task logs for a healthy rerun
    red_logs: dict[str, str]     # task logs for a rerun that still fails
    docs: list[dict[str, Any]]   # RAG corpus for this incident
    snapshot: dict[str, Any]     # spec consumed by gen_snapshot
    sim: dict[str, Any]          # deterministic scripted-agent content
    guardrail: dict[str, Any]    # preventive guardrail (Immunize)
    # Optional: a param override (e.g. memory bump) that also fixes the failure.
    param_fix: Optional[dict[str, Any]] = None

    @property
    def generated_snapshot_path(self) -> str:
        return str(DATA_DIR / f"snapshot_{self.id}.png")

    @property
    def custom_snapshot_path(self) -> str | None:
        for ext in _CUSTOM_EXTS:
            p = CUSTOM_DIR / f"{self.id}{ext}"
            if p.exists():
                return str(p)
        return None

    @property
    def snapshot_path(self) -> str:
        """The image Gemma 4 vision reads - a user-dropped custom dashboard if
        present, otherwise the auto-generated one."""
        return self.custom_snapshot_path or self.generated_snapshot_path


# --------------------------------------------------------------------------- #
# Shared baseline of 3 healthy historical runs for a job.
# --------------------------------------------------------------------------- #
def _healthy_history(job_id: str, base_duration: int) -> list[dict[str, Any]]:
    return [
        {"run_id": f"{job_id}_h{n}", "job_id": job_id, "status": "success",
         "started_at": _ago(d * 86400), "duration_s": base_duration + n,
         "failed_task": None, "trigger": "schedule"}
        for n, d in ((1, 3), (2, 2), (3, 1))
    ]


# --------------------------------------------------------------------------- #
# Scenario 1: OOMKill after a memory-cut config change (the original incident)
# --------------------------------------------------------------------------- #
_OOM_JOB = "acmeshop_nightly_etl"
_OOM_CULPRIT = "chg_8f2a1c"
_OOM_GOOD_MB, _OOM_BAD_MB = 8192, 2048

_oom = Scenario(
    id="oom_memory_cut",
    title="acmeshop_nightly_etl failed at transform (OOMKilled)",
    summary="Scheduled nightly run failed; transform task errored after 37s.",
    job_id=_OOM_JOB,
    dag=["ingest", "transform", "load"],
    failed_task="transform",
    failed_run_id="run_2004",
    runs=_healthy_history(_OOM_JOB, 139) + [
        {"run_id": "run_2004", "job_id": _OOM_JOB, "status": "failed",
         "started_at": _ago(600), "duration_s": 37, "failed_task": "transform",
         "trigger": "schedule"},
    ],
    logs={
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
    },
    metrics={"task_id": "transform", "metric": "memory_mb", "limit": _OOM_BAD_MB,
             "unit": "MB", "oom": True,
             "points": _series("memory_mb", _OOM_BAD_MB)},
    config_changes=[
        {"id": "chg_4b91de", "author": "maria@acmeshop.io", "ts": _ago(9 * 86400),
         "summary": "Add retry policy to load task",
         "diff": "+ load.retries: 3\n+ load.retry_delay: 60s"},
        {"id": "chg_7c30aa", "author": "deploybot", "ts": _ago(5 * 86400),
         "summary": "Bump base image to python:3.11-slim",
         "diff": "- image: python:3.10-slim\n+ image: python:3.11-slim"},
        {"id": _OOM_CULPRIT, "author": "costopt-bot", "ts": _ago(3600),
         "summary": "Reduce worker memory to cut cloud spend",
         "diff": f"  transform:\n-   worker_memory_mb: {_OOM_GOOD_MB}\n+   worker_memory_mb: {_OOM_BAD_MB}"},
    ],
    culprit_change_id=_OOM_CULPRIT,
    cost_per_min=900.0,
    param_fix={"keys": ["worker_memory_mb", "memory_mb"], "min": _OOM_GOOD_MB,
               "message": f"Applied override worker_memory_mb>={_OOM_GOOD_MB} for next run."},
    green_logs={
        "ingest": "OK ingested 1,240,338 rows",
        "transform": "OK transformed 1,240,338 rows (peak mem 6,912MB)",
        "load": "OK loaded 1,240,338 rows into warehouse.checkout_facts",
    },
    red_logs={
        "ingest": "OK ingested 1,240,338 rows",
        "transform": "ERROR: transform OOMKilled (memory limit exceeded). Process killed by cgroup.",
    },
    docs=[
        {"id": "rb_oom_transform", "namespace": "sre", "kind": "runbook",
         "title": "Runbook: transform OOMKilled",
         "text": ("Runbook: ETL transform task OOMKilled. Symptom: transform stage fails with "
                  "'OOMKilled' or 'memory limit exceeded'. Common cause: a recent config change "
                  "lowered worker_memory_mb below the working-set size (~7GB for nightly volumes). "
                  "Resolution: revert the offending config change to restore worker_memory_mb to "
                  "8192, or override worker_memory_mb for the run, then rerun. Do NOT simply rerun "
                  "without restoring memory; the failure is deterministic, not transient.")},
        {"id": "inc_1042", "namespace": "sre", "kind": "incident",
         "title": "INC-1042 post-mortem",
         "text": ("Past incident INC-1042 (resolved): acmeshop_nightly_etl transform OOMKilled "
                  "after a cost-optimization change reduced worker_memory_mb from 8192 to 4096. "
                  "Resolution: reverted the config change and reran; pipeline went green. Time to "
                  "resolve: 26 minutes. Lesson: route memory-affecting config changes through SRE review.")},
        {"id": "rb_connection_pool", "namespace": "sre", "kind": "runbook",
         "title": "Runbook: connection pool",
         "text": ("Runbook: database connection pool exhausted. Symptom: 'connection pool exhausted' "
                  "errors and rising p99 latency. Resolution: increase pool size or roll back the "
                  "change that reduced it. (Distractor for memory incidents.)")},
    ],
    snapshot={
        "title": "acmeshop_nightly_etl - run_2004",
        "subtitle": "schedule - FAILED after 37s",
        "sev": "SEV-2",
        "stages": [("ingest", "success", "ok"), ("transform", "FAILED - OOMKilled", "fail"),
                   ("load", "skipped", "skip")],
        "panel_title": "transform - worker memory",
        "limit": _OOM_BAD_MB,
        "unit": "MB",
        "limit_label": "worker_memory_limit 2048MB",
        "peg": True,
        "error_line": "ERROR transform OOMKilled: memory limit 2048MB exceeded - killed by cgroup (signal 9)",
        "stats": [("Peak mem", "2048 MB"), ("Healthy peak", "6912 MB"), ("Failed in", "37s")],
    },
    sim={
        "vision": ("The snapshot shows the acmeshop_nightly_etl DAG with ingest green, transform "
                   "RED (FAILED, OOMKilled), and load skipped. The memory panel is pegged at a "
                   "2048MB worker_memory_limit - a strong signal of a memory cap, not a data problem."),
        "triage": ("A scheduled run of acmeshop_nightly_etl failed at the transform task. I'll engage "
                   "the telemetry, change, and knowledge specialists, then synthesize."),
        "telemetry_act": [("get_job_runs", {"job_id": _OOM_JOB, "limit": 5}),
                          ("get_job_logs", {}),
                          ("get_metrics", {"task_id": "transform", "metric": "memory_mb"})],
        "telemetry_summary": ("transform was OOMKilled: worker memory pegged at the 2048MB limit, while "
                              "the last 3 nightly runs succeeded with a ~6.9GB peak. The memory ceiling, "
                              "not the data, is the problem."),
        "change_act": [("list_recent_config_changes", {"limit": 5}),
                       ("config_diff", {"change_id": _OOM_CULPRIT})],
        "change_summary": (f"Config change {_OOM_CULPRIT} by costopt-bot ~1h ago cut transform "
                           "worker_memory_mb from 8192 to 2048 - immediately before the failure."),
        "knowledge_act": [("query_runbook", {"query": "transform task OOMKilled memory limit exceeded"}),
                          ("find_similar_failures", {"query": "nightly etl transform OOM after config change"})],
        "knowledge_summary": ("The OOM runbook and past incident INC-1042 agree: revert the memory-cutting "
                              "config change (or raise the limit) and rerun. The failure is deterministic."),
        "synthesis": {
            "root_cause": (f"Config change {_OOM_CULPRIT} reduced transform worker_memory_mb from 8192 "
                           "to 2048, causing the transform task to be OOMKilled."),
            "confidence": 0.93,
            "hypotheses": [
                {"claim": "Lowered worker memory (8192->2048MB) caused transform OOMKill.",
                 "likelihood": 0.93,
                 "evidence": [
                     {"source": "job_log", "ref": "run_2004",
                      "detail": "transform OOMKilled: memory limit 2048MB exceeded"},
                     {"source": "metrics", "ref": "transform.memory_mb",
                      "detail": "Memory pegged at 2048MB limit vs ~6.9GB healthy peak"},
                     {"source": "config_change", "ref": _OOM_CULPRIT,
                      "detail": "worker_memory_mb 8192->2048 by costopt-bot 1h before failure"},
                     {"source": "incident", "ref": "INC-1042",
                      "detail": "Identical past OOM resolved by reverting the memory change"}]},
                {"claim": "Transient/data-volume issue (rerun would fix).", "likelihood": 0.05,
                 "evidence": [{"source": "runbook", "ref": "rb_oom_transform",
                               "detail": "Failure is deterministic, not transient; plain rerun fails again"}]},
            ],
            "proposed_actions": [
                {"action": "revert_config", "args": {"change_id": _OOM_CULPRIT}, "risk_tier": 2,
                 "rationale": "Restore worker_memory_mb to 8192 by reverting the offending change."},
                {"action": "rerun_job", "args": {"job_id": _OOM_JOB}, "risk_tier": 2,
                 "rationale": "Rerun the nightly ETL to verify recovery after the fix."},
            ],
        },
        "candidates": [
            {"action": "rerun_job", "args": {"job_id": _OOM_JOB}, "label": "Rerun as-is",
             "predicted_green": 0.07, "risk_tier": 2, "confidence": 0.9,
             "predicted_outcome": "Fails again - OOM is deterministic, memory cap unchanged."},
            {"action": "retry_with_params", "args": {"job_id": _OOM_JOB, "params": {"worker_memory_mb": 8192}},
             "label": "Override memory for one run", "predicted_green": 0.88, "risk_tier": 2, "confidence": 0.82,
             "predicted_outcome": "Likely green, but leaves the bad config in place to recur."},
            {"action": "revert_config", "args": {"change_id": _OOM_CULPRIT}, "label": "Revert culprit + rerun",
             "predicted_green": 0.96, "risk_tier": 2, "confidence": 0.93,
             "predicted_outcome": "Green and durable - restores 8192MB and removes the regression."},
        ],
        "guardrail": {
            "title": "Block memory cuts below the working-set floor",
            "policy": ("CI policy: reject any pipeline config change that sets transform.worker_memory_mb "
                       "below 4096; require SRE review for any memory-affecting change."),
            "rationale": ("INC-1042 and this incident were both caused by automated memory cuts. A CI gate "
                          "makes the entire OOM class impossible to ship again."),
            "artifact_kind": "pull_request",
        },
    },
    guardrail={},
)
_oom.guardrail = _oom.sim["guardrail"]


# --------------------------------------------------------------------------- #
# Scenario 2: Schema / data-contract drift breaks the transform
# --------------------------------------------------------------------------- #
_SCH_JOB = "acmeshop_orders_sync"
_SCH_CULPRIT = "chg_3d77b0"

_schema = Scenario(
    id="schema_drift",
    title="acmeshop_orders_sync failed at transform (schema contract violation)",
    summary="Hourly orders sync failed; transform rejected every row on a not-null contract.",
    job_id=_SCH_JOB,
    dag=["ingest", "transform", "load"],
    failed_task="transform",
    failed_run_id="run_5567",
    runs=_healthy_history(_SCH_JOB, 88) + [
        {"run_id": "run_5567", "job_id": _SCH_JOB, "status": "failed",
         "started_at": _ago(420), "duration_s": 19, "failed_task": "transform",
         "trigger": "schedule"},
    ],
    logs={
        "run_5567": {
            "ingest": "OK ingested 412,889 rows from orders.v2 source",
            "transform": (
                "INFO starting transform stage (contract=orders_contract@v3)\n"
                "INFO validating columns against contract...\n"
                "ERROR column 'customer_id' not found; source now emits 'cust_id'\n"
                "ERROR data-contract assertion failed: not-null column 'customer_id' "
                "missing in 412,889/412,889 rows.\n"
                "ERROR task 'transform' failed; downstream 'load' skipped."
            ),
            "load": "SKIPPED (upstream transform failed)",
        },
    },
    metrics={"task_id": "transform", "metric": "rows_rejected", "limit": 412889,
             "unit": "rows", "oom": False,
             "points": _series("rows_rejected", 412889, peg=True)},
    config_changes=[
        {"id": "chg_1a02ff", "author": "deploybot", "ts": _ago(6 * 86400),
         "summary": "Rotate warehouse credentials", "diff": "~ load.warehouse.secret_ref: v4 -> v5"},
        {"id": "chg_9e54c1", "author": "priya@acmeshop.io", "ts": _ago(2 * 86400),
         "summary": "Increase ingest batch size", "diff": "- ingest.batch_size: 5000\n+ ingest.batch_size: 8000"},
        {"id": _SCH_CULPRIT, "author": "data-platform-bot", "ts": _ago(900),
         "summary": "Point orders source at v2 endpoint (renames customer_id -> cust_id)",
         "diff": ("  ingest.source:\n-   url: /orders/v1\n+   url: /orders/v2\n"
                  "  # NOTE: v2 renames customer_id -> cust_id (breaking)")},
    ],
    culprit_change_id=_SCH_CULPRIT,
    cost_per_min=650.0,
    green_logs={
        "ingest": "OK ingested 412,889 rows from orders.v1 source",
        "transform": "OK transformed 412,889 rows; contract orders_contract@v3 satisfied",
        "load": "OK loaded 412,889 rows into warehouse.orders_facts",
    },
    red_logs={
        "ingest": "OK ingested 412,889 rows from orders.v2 source",
        "transform": "ERROR: data-contract assertion failed: not-null column 'customer_id' missing (source emits 'cust_id').",
    },
    docs=[
        {"id": "rb_schema_contract", "namespace": "sre", "kind": "runbook",
         "title": "Runbook: data-contract / schema violations",
         "text": ("Runbook: transform data-contract assertion failed. Symptom: transform rejects rows "
                  "with 'column not found' or 'not-null column missing'. Common cause: an upstream "
                  "source/endpoint change renamed or retyped a column. Resolution: revert the source "
                  "change (or add an explicit column mapping) so the contract is satisfied, then rerun. "
                  "A plain rerun keeps failing because the schema mismatch is deterministic.")},
        {"id": "inc_0931", "namespace": "sre", "kind": "incident",
         "title": "INC-0931 post-mortem",
         "text": ("Past incident INC-0931 (resolved): orders_sync transform failed after a source "
                  "endpoint bump renamed 'order_ts' to 'created_at'. Resolution: reverted the source "
                  "pointer and reran; pipeline went green. Lesson: schema changes need a contract check in CI.")},
        {"id": "rb_load_warehouse", "namespace": "sre", "kind": "runbook",
         "title": "Runbook: load failures",
         "text": ("Runbook: load stage warehouse write failures. Symptom: 'load' task errors writing to "
                  "the warehouse. Resolution: check credentials and disk. (Distractor; unrelated to "
                  "transform contract violations.)")},
    ],
    snapshot={
        "title": "acmeshop_orders_sync - run_5567",
        "subtitle": "schedule - FAILED after 19s",
        "sev": "SEV-2",
        "stages": [("ingest", "success", "ok"), ("transform", "FAILED - contract", "fail"),
                   ("load", "skipped", "skip")],
        "panel_title": "transform - rows rejected by contract",
        "limit": 412889,
        "unit": "rows",
        "limit_label": "412,889 / 412,889 rows rejected",
        "peg": True,
        "error_line": "ERROR data-contract: not-null column 'customer_id' missing - source emits 'cust_id'",
        "stats": [("Rows rejected", "100%"), ("Contract", "orders@v3"), ("Failed in", "19s")],
    },
    sim={
        "vision": ("The snapshot shows acmeshop_orders_sync with ingest green, transform RED (contract "
                   "failure), load skipped. The bottom panel shows 100% of rows rejected by the data "
                   "contract - a schema mismatch, not a resource problem."),
        "triage": ("acmeshop_orders_sync failed at transform with a data-contract violation. I'll have "
                   "telemetry pull the failure logs, change inspect recent source changes, and knowledge "
                   "check the schema runbook."),
        "telemetry_act": [("get_job_runs", {"job_id": _SCH_JOB, "limit": 5}),
                          ("get_job_logs", {}),
                          ("get_metrics", {"task_id": "transform", "metric": "rows_rejected"})],
        "telemetry_summary": ("transform rejected all 412,889 rows: the contract expected a not-null "
                              "'customer_id' but the source now emits 'cust_id'. Ingest succeeded, so the "
                              "data arrived - the schema is the problem."),
        "change_act": [("list_recent_config_changes", {"limit": 5}),
                       ("config_diff", {"change_id": _SCH_CULPRIT})],
        "change_summary": (f"Config change {_SCH_CULPRIT} by data-platform-bot ~15m ago repointed the "
                           "orders source from v1 to v2, which renames customer_id -> cust_id - the "
                           "breaking change immediately before the failure."),
        "knowledge_act": [("query_runbook", {"query": "transform data contract not-null column missing schema"}),
                          ("find_similar_failures", {"query": "orders sync schema rename column transform failure"})],
        "knowledge_summary": ("The schema-contract runbook and INC-0931 agree: revert the source change "
                              "(or add a column mapping) so the contract is satisfied, then rerun."),
        "synthesis": {
            "root_cause": (f"Config change {_SCH_CULPRIT} repointed the orders source to v2, which renamed "
                           "'customer_id' to 'cust_id', so the transform's not-null data contract rejected "
                           "every row."),
            "confidence": 0.91,
            "hypotheses": [
                {"claim": "Source v2 column rename (customer_id->cust_id) broke the data contract.",
                 "likelihood": 0.91,
                 "evidence": [
                     {"source": "job_log", "ref": "run_5567",
                      "detail": "not-null column 'customer_id' missing in 412,889/412,889 rows"},
                     {"source": "config_change", "ref": _SCH_CULPRIT,
                      "detail": "source repointed v1->v2 (renames customer_id->cust_id) 15m before failure"},
                     {"source": "incident", "ref": "INC-0931",
                      "detail": "Prior schema-rename failure resolved by reverting the source pointer"}]},
                {"claim": "Warehouse credential rotation (chg_1a02ff) caused it.", "likelihood": 0.04,
                 "evidence": [{"source": "job_log", "ref": "run_5567",
                               "detail": "Failure is at transform contract validation, not the load write"}]},
            ],
            "proposed_actions": [
                {"action": "revert_config", "args": {"change_id": _SCH_CULPRIT}, "risk_tier": 2,
                 "rationale": "Revert the source endpoint change so customer_id is present and the contract passes."},
                {"action": "rerun_job", "args": {"job_id": _SCH_JOB}, "risk_tier": 2,
                 "rationale": "Rerun the orders sync to verify the contract passes after the revert."},
            ],
        },
        "candidates": [
            {"action": "rerun_job", "args": {"job_id": _SCH_JOB}, "label": "Rerun as-is",
             "predicted_green": 0.05, "risk_tier": 2, "confidence": 0.92,
             "predicted_outcome": "Fails again - the source still emits cust_id; mismatch is deterministic."},
            {"action": "revert_config", "args": {"change_id": _SCH_CULPRIT}, "label": "Revert source change + rerun",
             "predicted_green": 0.95, "risk_tier": 2, "confidence": 0.91,
             "predicted_outcome": "Green - restores customer_id so the not-null contract is satisfied."},
        ],
        "guardrail": {
            "title": "Require a schema-contract check before source changes ship",
            "policy": ("CI policy: any change to ingest.source must pass a data-contract diff test against "
                       "the current orders_contract; block merges that drop or rename a not-null column."),
            "rationale": ("Both INC-0931 and this incident were silent schema renames. A contract check in CI "
                          "turns a production outage into a failed build."),
            "artifact_kind": "pull_request",
        },
    },
    guardrail={},
)
_schema.guardrail = _schema.sim["guardrail"]


# --------------------------------------------------------------------------- #
# Scenario 3: Bad dependency / image bump regression
# --------------------------------------------------------------------------- #
_DEP_JOB = "acmeshop_reco_features"
_DEP_CULPRIT = "chg_b22e74"

_dep = Scenario(
    id="dependency_bump",
    title="acmeshop_reco_features failed at transform (dependency regression)",
    summary="Feature build failed; transform raised an ArrowInvalid after a pyarrow bump.",
    job_id=_DEP_JOB,
    dag=["ingest", "transform", "load"],
    failed_task="transform",
    failed_run_id="run_8123",
    runs=_healthy_history(_DEP_JOB, 205) + [
        {"run_id": "run_8123", "job_id": _DEP_JOB, "status": "failed",
         "started_at": _ago(300), "duration_s": 12, "failed_task": "transform",
         "trigger": "schedule"},
    ],
    logs={
        "run_8123": {
            "ingest": "OK ingested 2,004,551 events for feature build",
            "transform": (
                "INFO starting transform stage (image=features:2025.06.2)\n"
                "INFO building feature frames with pyarrow 17.0.0...\n"
                "ERROR pyarrow.lib.ArrowInvalid: 'use_legacy_dataset' is no longer a "
                "valid argument to write_table (removed in pyarrow 16).\n"
                "ERROR task 'transform' failed at 12s; downstream 'load' skipped."
            ),
            "load": "SKIPPED (upstream transform failed)",
        },
    },
    metrics={"task_id": "transform", "metric": "task_error_rate_pct", "limit": 100,
             "unit": "%", "oom": False,
             "points": [{"t": i * 2, "task_error_rate_pct": 0 if i < 6 else 100} for i in range(12)]},
    config_changes=[
        {"id": "chg_55aa10", "author": "sam@acmeshop.io", "ts": _ago(4 * 86400),
         "summary": "Add new ranking feature", "diff": "+ transform.features: [ctr_7d, dwell_30d]"},
        {"id": "chg_2f8c93", "author": "maria@acmeshop.io", "ts": _ago(86400),
         "summary": "Increase reco load parallelism", "diff": "- load.parallelism: 4\n+ load.parallelism: 8"},
        {"id": _DEP_CULPRIT, "author": "deploybot", "ts": _ago(1200),
         "summary": "Bump transform image (pyarrow 14 -> 17)",
         "diff": ("  transform:\n-   image: features:2025.05.9   # pyarrow 14.0.2\n"
                  "+   image: features:2025.06.2   # pyarrow 17.0.0 (breaking)")},
    ],
    culprit_change_id=_DEP_CULPRIT,
    cost_per_min=480.0,
    green_logs={
        "ingest": "OK ingested 2,004,551 events for feature build",
        "transform": "OK built feature frames (pyarrow 14.0.2); 2,004,551 rows",
        "load": "OK loaded feature frames into warehouse.reco_features",
    },
    red_logs={
        "ingest": "OK ingested 2,004,551 events for feature build",
        "transform": "ERROR: pyarrow.lib.ArrowInvalid: 'use_legacy_dataset' removed in pyarrow 16 (image still on 17).",
    },
    docs=[
        {"id": "rb_dependency_regression", "namespace": "sre", "kind": "runbook",
         "title": "Runbook: dependency / image bump regression",
         "text": ("Runbook: transform fails immediately after an image or library bump with an "
                  "ImportError/AttributeError/ArrowInvalid. Common cause: a base-image or pinned-library "
                  "upgrade dropped or changed an API the job relies on. Resolution: revert the image/lib "
                  "bump to the last-good pin and rerun; then fix forward behind a canary. A plain rerun "
                  "keeps failing because the broken dependency is still installed.")},
        {"id": "inc_0777", "namespace": "sre", "kind": "incident",
         "title": "INC-0777 post-mortem",
         "text": ("Past incident INC-0777 (resolved): reco_features transform broke after a numpy 2.0 bump "
                  "removed a deprecated alias. Resolution: reverted the image pin and reran green. Lesson: "
                  "library bumps must go through a canary build before the scheduled job.")},
        {"id": "rb_flaky_network", "namespace": "sre", "kind": "runbook",
         "title": "Runbook: transient ingest failures",
         "text": ("Runbook: transient network failures in ingest. Symptom: intermittent timeouts in ingest "
                  "that pass on retry. Resolution: rerun as-is. (Distractor; applies only to network "
                  "timeouts, not dependency errors.)")},
    ],
    snapshot={
        "title": "acmeshop_reco_features - run_8123",
        "subtitle": "schedule - FAILED after 12s",
        "sev": "SEV-3",
        "stages": [("ingest", "success", "ok"), ("transform", "FAILED - ArrowInvalid", "fail"),
                   ("load", "skipped", "skip")],
        "panel_title": "transform - task error rate",
        "limit": 100,
        "unit": "%",
        "limit_label": "0 -> 100% error after image bump",
        "peg": True,
        "error_line": "ERROR pyarrow.lib.ArrowInvalid: 'use_legacy_dataset' removed in pyarrow 16 (image on 17)",
        "stats": [("Error rate", "100%"), ("pyarrow", "14 -> 17"), ("Failed in", "12s")],
    },
    sim={
        "vision": ("The snapshot shows acmeshop_reco_features with ingest green, transform RED, load "
                   "skipped. The error-rate panel jumps from 0% to 100% at a fixed point - a hard, "
                   "immediate failure consistent with a code/dependency break, not data or memory."),
        "triage": ("acmeshop_reco_features failed at transform almost immediately (12s). That pattern "
                   "smells like a dependency/image regression. I'll engage all three specialists."),
        "telemetry_act": [("get_job_runs", {"job_id": _DEP_JOB, "limit": 5}),
                          ("get_job_logs", {}),
                          ("get_metrics", {"task_id": "transform", "metric": "task_error_rate_pct"})],
        "telemetry_summary": ("transform failed at 12s with pyarrow.lib.ArrowInvalid about 'use_legacy_dataset' "
                              "being removed in pyarrow 16. Error rate went 0->100% instantly - a code break, "
                              "not data volume."),
        "change_act": [("list_recent_config_changes", {"limit": 5}),
                       ("config_diff", {"change_id": _DEP_CULPRIT})],
        "change_summary": (f"Config change {_DEP_CULPRIT} by deploybot ~20m ago bumped the transform image "
                           "from pyarrow 14.0.2 to 17.0.0 - the breaking upgrade right before the failure."),
        "knowledge_act": [("query_runbook", {"query": "transform ArrowInvalid pyarrow dependency image bump regression"}),
                          ("find_similar_failures", {"query": "reco features transform broke after library bump"})],
        "knowledge_summary": ("The dependency-regression runbook and INC-0777 agree: revert the image/library "
                              "bump to the last-good pin and rerun, then fix forward behind a canary."),
        "synthesis": {
            "root_cause": (f"Config change {_DEP_CULPRIT} bumped the transform image to pyarrow 17.0.0, which "
                           "removed the 'use_legacy_dataset' argument the job uses, so transform raised "
                           "ArrowInvalid on every run."),
            "confidence": 0.9,
            "hypotheses": [
                {"claim": "pyarrow 14->17 image bump removed an API the transform relies on.",
                 "likelihood": 0.9,
                 "evidence": [
                     {"source": "job_log", "ref": "run_8123",
                      "detail": "ArrowInvalid: 'use_legacy_dataset' removed in pyarrow 16"},
                     {"source": "config_change", "ref": _DEP_CULPRIT,
                      "detail": "transform image bumped pyarrow 14.0.2 -> 17.0.0, 20m before failure"},
                     {"source": "incident", "ref": "INC-0777",
                      "detail": "Prior library-bump regression resolved by reverting the image pin"}]},
                {"claim": "New ranking feature (chg_55aa10) caused it.", "likelihood": 0.06,
                 "evidence": [{"source": "job_log", "ref": "run_8123",
                               "detail": "Error is in pyarrow write_table, not feature logic"}]},
            ],
            "proposed_actions": [
                {"action": "revert_config", "args": {"change_id": _DEP_CULPRIT}, "risk_tier": 2,
                 "rationale": "Revert the image to the last-good pyarrow 14.0.2 pin."},
                {"action": "rerun_job", "args": {"job_id": _DEP_JOB}, "risk_tier": 2,
                 "rationale": "Rerun the feature build to verify recovery on the restored image."},
            ],
        },
        "candidates": [
            {"action": "rerun_job", "args": {"job_id": _DEP_JOB}, "label": "Rerun as-is",
             "predicted_green": 0.04, "risk_tier": 2, "confidence": 0.93,
             "predicted_outcome": "Fails again - the broken pyarrow 17 image is still deployed."},
            {"action": "revert_config", "args": {"change_id": _DEP_CULPRIT}, "label": "Revert image bump + rerun",
             "predicted_green": 0.94, "risk_tier": 2, "confidence": 0.9,
             "predicted_outcome": "Green - restores the pyarrow 14.0.2 image the job is compatible with."},
        ],
        "guardrail": {
            "title": "Gate image/library bumps behind a canary build",
            "policy": ("CI policy: any change to a task image or pinned dependency must pass a canary run of "
                       "the affected DAG before it can target the scheduled job; require SRE review."),
            "rationale": ("INC-0777 and this incident were both untested dependency bumps. A mandatory canary "
                          "catches the break before it reaches production."),
            "artifact_kind": "pull_request",
        },
    },
    guardrail={},
)
_dep.guardrail = _dep.sim["guardrail"]


# --------------------------------------------------------------------------- #
# Scenario 4: Vendor rate-limit (HTTP 429) in ingest after a concurrency bump
# --------------------------------------------------------------------------- #
_RL_JOB = "acmeshop_partner_ingest"
_RL_CULPRIT = "chg_e90f12"

_ratelimit = Scenario(
    id="vendor_ratelimit",
    title="acmeshop_partner_ingest failed at ingest (vendor HTTP 429)",
    summary="Partner ingest failed; the vendor API returned HTTP 429 after a concurrency bump.",
    job_id=_RL_JOB,
    dag=["ingest", "transform", "load"],
    failed_task="ingest",
    failed_run_id="run_3310",
    runs=_healthy_history(_RL_JOB, 96) + [
        {"run_id": "run_3310", "job_id": _RL_JOB, "status": "failed",
         "started_at": _ago(240), "duration_s": 54, "failed_task": "ingest",
         "trigger": "schedule"},
    ],
    logs={
        "run_3310": {
            "ingest": (
                "INFO starting ingest from partner API (concurrency=32)\n"
                "INFO opened 32 parallel connections to api.partner.example\n"
                "WARN HTTP 429 Too Many Requests (Retry-After: 30) x214\n"
                "ERROR vendor rate limit exceeded: 32 concurrent > 8 contracted; "
                "ingest aborted after 214 consecutive 429s.\n"
                "ERROR task 'ingest' failed; downstream 'transform' and 'load' skipped."
            ),
            "transform": "SKIPPED (upstream ingest failed)",
            "load": "SKIPPED (upstream ingest failed)",
        },
    },
    metrics={"task_id": "ingest", "metric": "http_429_per_min", "limit": 240,
             "unit": "responses/min", "oom": False,
             "points": _series("http_429_per_min", 240, peg=True)},
    config_changes=[
        {"id": "chg_77c4a1", "author": "deploybot", "ts": _ago(7 * 86400),
         "summary": "Add partner ingest retries", "diff": "+ ingest.retries: 2"},
        {"id": "chg_0b9d3e", "author": "lee@acmeshop.io", "ts": _ago(3 * 86400),
         "summary": "Move ingest to new region", "diff": "- ingest.region: us-east-1\n+ ingest.region: us-west-2"},
        {"id": _RL_CULPRIT, "author": "perf-bot", "ts": _ago(1500),
         "summary": "Raise ingest concurrency to speed up partner sync",
         "diff": "  ingest:\n-   concurrency: 4\n+   concurrency: 32   # exceeds 8 contracted"},
    ],
    culprit_change_id=_RL_CULPRIT,
    cost_per_min=720.0,
    green_logs={
        "ingest": "OK ingested partner feed at concurrency=4 (0 rate-limit responses)",
        "transform": "OK transformed partner records",
        "load": "OK loaded partner records into warehouse.partner_facts",
    },
    red_logs={
        "ingest": "ERROR: vendor rate limit exceeded (HTTP 429 x214); concurrency still above the contracted ceiling.",
        "transform": "SKIPPED (upstream ingest failed)",
    },
    docs=[
        {"id": "rb_vendor_ratelimit", "namespace": "sre", "kind": "runbook",
         "title": "Runbook: vendor HTTP 429 rate limiting",
         "text": ("Runbook: ingest fails with HTTP 429 'Too Many Requests'. Common cause: a concurrency or "
                  "request-rate increase pushed calls past the vendor's contracted limit. Resolution: revert "
                  "the concurrency bump back under the contracted ceiling (or add backoff), then rerun. A "
                  "plain rerun at the same concurrency keeps getting 429'd.")},
        {"id": "inc_0610", "namespace": "sre", "kind": "incident",
         "title": "INC-0610 post-mortem",
         "text": ("Past incident INC-0610 (resolved): partner_ingest got 429-throttled after concurrency was "
                  "raised from 4 to 24. Resolution: reverted concurrency to 4 and reran green. Lesson: enforce "
                  "a per-vendor concurrency budget aligned to the contract.")},
        {"id": "rb_connection_pool2", "namespace": "sre", "kind": "runbook",
         "title": "Runbook: connection pool",
         "text": ("Runbook: database connection pool exhausted. Resolution: increase pool size. (Distractor; "
                  "unrelated to vendor HTTP 429 throttling.)")},
    ],
    snapshot={
        "title": "acmeshop_partner_ingest - run_3310",
        "subtitle": "schedule - FAILED after 54s",
        "sev": "SEV-2",
        "stages": [("ingest", "FAILED - HTTP 429", "fail"), ("transform", "skipped", "skip"),
                   ("load", "skipped", "skip")],
        "panel_title": "ingest - vendor HTTP 429 / min",
        "limit": 240,
        "unit": "429/min",
        "limit_label": "429s spiking after concurrency 4 -> 32",
        "peg": True,
        "error_line": "ERROR vendor rate limit: HTTP 429 x214 - 32 concurrent > 8 contracted; ingest aborted",
        "stats": [("Peak 429/min", "240"), ("Concurrency", "4 -> 32"), ("Failed in", "54s")],
    },
    sim={
        "vision": ("The snapshot shows acmeshop_partner_ingest with the FIRST stage, ingest, RED (HTTP 429) "
                   "and transform/load skipped. The panel shows vendor 429 responses spiking - the partner "
                   "API is throttling us, not an internal resource issue."),
        "triage": ("acmeshop_partner_ingest failed right at the ingest stage with vendor 429s. I'll have "
                   "telemetry confirm the throttling, change look for a recent concurrency/rate change, and "
                   "knowledge pull the rate-limit runbook."),
        "telemetry_act": [("get_job_runs", {"job_id": _RL_JOB, "limit": 5}),
                          ("get_job_logs", {}),
                          ("get_metrics", {"task_id": "ingest", "metric": "http_429_per_min"})],
        "telemetry_summary": ("ingest opened 32 parallel connections and got 214 HTTP 429s ('32 concurrent > 8 "
                              "contracted'). The vendor is rate-limiting us; the failure is at ingest, not "
                              "transform/load."),
        "change_act": [("list_recent_config_changes", {"limit": 5}),
                       ("config_diff", {"change_id": _RL_CULPRIT})],
        "change_summary": (f"Config change {_RL_CULPRIT} by perf-bot ~25m ago raised ingest concurrency from 4 "
                           "to 32 - above the 8 contracted - immediately before the 429 storm."),
        "knowledge_act": [("query_runbook", {"query": "ingest HTTP 429 vendor rate limit concurrency too high"}),
                          ("find_similar_failures", {"query": "partner ingest 429 throttled concurrency raised"})],
        "knowledge_summary": ("The rate-limit runbook and INC-0610 agree: revert the concurrency bump back under "
                              "the contracted ceiling (or add backoff), then rerun."),
        "synthesis": {
            "root_cause": (f"Config change {_RL_CULPRIT} raised ingest concurrency from 4 to 32, exceeding the "
                           "vendor's contracted limit of 8, so the partner API returned HTTP 429 and the ingest "
                           "task failed."),
            "confidence": 0.92,
            "hypotheses": [
                {"claim": "Concurrency 4->32 exceeded the vendor's contracted rate, triggering 429s.",
                 "likelihood": 0.92,
                 "evidence": [
                     {"source": "job_log", "ref": "run_3310",
                      "detail": "HTTP 429 x214; '32 concurrent > 8 contracted'"},
                     {"source": "metrics", "ref": "ingest.http_429_per_min",
                      "detail": "429 responses/min spiked after the concurrency change"},
                     {"source": "config_change", "ref": _RL_CULPRIT,
                      "detail": "ingest concurrency 4->32 by perf-bot 25m before failure"},
                     {"source": "incident", "ref": "INC-0610",
                      "detail": "Identical 429 throttling resolved by reverting concurrency"}]},
                {"claim": "Region move (chg_0b9d3e) caused it.", "likelihood": 0.05,
                 "evidence": [{"source": "job_log", "ref": "run_3310",
                               "detail": "Errors are vendor 429s, not connectivity/region errors"}]},
            ],
            "proposed_actions": [
                {"action": "revert_config", "args": {"change_id": _RL_CULPRIT}, "risk_tier": 2,
                 "rationale": "Revert ingest concurrency back to 4, under the contracted ceiling."},
                {"action": "rerun_job", "args": {"job_id": _RL_JOB}, "risk_tier": 2,
                 "rationale": "Rerun the partner ingest to verify the 429s clear after the revert."},
            ],
        },
        "candidates": [
            {"action": "rerun_job", "args": {"job_id": _RL_JOB}, "label": "Rerun as-is",
             "predicted_green": 0.06, "risk_tier": 2, "confidence": 0.92,
             "predicted_outcome": "Fails again - still 32 concurrent against an 8-request ceiling."},
            {"action": "revert_config", "args": {"change_id": _RL_CULPRIT}, "label": "Revert concurrency + rerun",
             "predicted_green": 0.95, "risk_tier": 2, "confidence": 0.92,
             "predicted_outcome": "Green - concurrency back to 4 stays under the contracted limit."},
        ],
        "guardrail": {
            "title": "Enforce a per-vendor concurrency budget",
            "policy": ("CI policy: reject any change that raises ingest.concurrency above the per-vendor "
                       "contracted ceiling (partner API = 8); require an explicit contract update + SRE review."),
            "rationale": ("INC-0610 and this incident were both concurrency bumps past the contract. A budget "
                          "check in CI makes vendor 429 storms unshippable."),
            "artifact_kind": "pull_request",
        },
    },
    guardrail={},
)
_ratelimit.guardrail = _ratelimit.sim["guardrail"]


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
SCENARIOS: dict[str, Scenario] = {
    _oom.id: _oom,
    _schema.id: _schema,
    _dep.id: _dep,
    _ratelimit.id: _ratelimit,
}

DEFAULT_SCENARIO_ID = _oom.id


def get_scenario(scenario_id: Optional[str]) -> Scenario:
    return SCENARIOS.get(scenario_id or DEFAULT_SCENARIO_ID, _oom)


def list_scenarios() -> list[dict[str, Any]]:
    """Lightweight metadata for the API / scenario picker."""
    return [
        {"id": s.id, "title": s.title, "summary": s.summary, "job_id": s.job_id,
         "failed_task": s.failed_task, "cost_per_min": s.cost_per_min}
        for s in SCENARIOS.values()
    ]
