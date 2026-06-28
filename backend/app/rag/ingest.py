"""Runbook + past-incident corpus and one-shot ingest into the vector store.

Docs carry a `namespace` used for permission-aware retrieval. The demo caller is
allowed the 'sre' and 'public' namespaces but NOT 'finance', so the finance doc
(a plausible distractor) is correctly never retrieved.
"""
from __future__ import annotations

from functools import lru_cache

from app.rag.vectorstore import Doc, VectorStore

# namespace -> docs. Each doc: (id, title, text)
CORPUS: list[Doc] = [
    Doc(
        id="rb_oom_transform",
        namespace="sre",
        text=(
            "Runbook: ETL transform task OOMKilled. Symptom: transform stage fails "
            "with 'OOMKilled' or 'memory limit exceeded'. Common cause: a recent "
            "config change lowered worker_memory_mb below the working-set size "
            "(~7GB for nightly volumes). Resolution: revert the offending config "
            "change to restore worker_memory_mb to 8192, or override worker_memory_mb "
            "for the run, then rerun the job. Do NOT simply rerun without restoring "
            "memory; the failure is deterministic, not transient."
        ),
        metadata={"title": "Runbook: transform OOMKilled", "kind": "runbook"},
    ),
    Doc(
        id="rb_connection_pool",
        namespace="sre",
        text=(
            "Runbook: database connection pool exhausted. Symptom: 'connection pool "
            "exhausted' errors and rising p99 latency. Cause: pool size too small or "
            "leaked connections. Resolution: increase pool size or roll back the "
            "change that reduced it. (Distractor for memory incidents.)"
        ),
        metadata={"title": "Runbook: connection pool", "kind": "runbook"},
    ),
    Doc(
        id="rb_flaky_network",
        namespace="sre",
        text=(
            "Runbook: transient network failures in ingest. Symptom: intermittent "
            "timeouts in the ingest stage that pass on retry. Resolution: rerun the "
            "job as-is; these are transient. Applies ONLY when logs show network "
            "timeouts, not memory errors."
        ),
        metadata={"title": "Runbook: transient ingest failures", "kind": "runbook"},
    ),
    Doc(
        id="inc_1042",
        namespace="sre",
        text=(
            "Past incident INC-1042 (resolved): acmeshop_nightly_etl transform "
            "OOMKilled after a cost-optimization change reduced worker_memory_mb "
            "from 8192 to 4096. Resolution: reverted the config change and reran; "
            "pipeline went green. Time to resolve: 26 minutes. Owner: maria. "
            "Lesson: route memory-affecting config changes through SRE review."
        ),
        metadata={"title": "INC-1042 post-mortem", "kind": "incident"},
    ),
    Doc(
        id="rb_load_warehouse",
        namespace="sre",
        text=(
            "Runbook: load stage warehouse write failures. Symptom: 'load' task "
            "errors writing to warehouse.checkout_facts. Resolution: check warehouse "
            "credentials and disk. (Distractor; unrelated to transform memory.)"
        ),
        metadata={"title": "Runbook: load failures", "kind": "runbook"},
    ),
    Doc(
        id="fin_budget_policy",
        namespace="finance",  # caller is NOT allowed this namespace
        text=(
            "Finance policy: cloud cost-optimization initiative Q3 mandates reducing "
            "worker memory allocations by 75% across batch jobs to cut spend. "
            "CONFIDENTIAL - finance namespace only."
        ),
        metadata={"title": "Finance cost policy", "kind": "policy"},
    ),
    Doc(
        id="pub_oncall",
        namespace="public",
        text=(
            "On-call overview: nightly ETL feeds the checkout analytics warehouse. "
            "A failed nightly run delays morning dashboards for the revenue team."
        ),
        metadata={"title": "On-call overview", "kind": "doc"},
    ),
]


@lru_cache
def get_vector_store() -> VectorStore:
    vs = VectorStore()
    vs.upsert(CORPUS)
    return vs
