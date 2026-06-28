"""End-to-end backend smoke test (runs against the simulated agent, no API key).

Validates: imports, snapshot generation, embeddings + permission-aware RAG,
the full investigation event stream, the approval gate, and gated remediation
with recovery verification.
"""
from __future__ import annotations

import asyncio
import sys

from app.agents.commander import Commander
from app.agents.schemas import IncidentStatus, IncidentTrigger
from app.pipeline.mock_backend import MockBackend
from app.rag.embeddings import get_embedder
from app.rag.ingest import get_vector_store
from app.tools import knowledge


async def main() -> int:
    print("== config / backends ==")
    emb = get_embedder()
    vs = get_vector_store()
    print(f"embedding backend = {emb.backend} (dim={emb.dim})")
    print(f"vector backend    = {vs.backend}")

    print("\n== permission-aware retrieval ==")
    res = knowledge.query_runbook("transform OOMKilled memory limit", top_k=5)
    ns = {r["namespace"] for r in res["results"]}
    print(f"namespaces returned = {ns}")
    assert "finance" not in ns, "ACL LEAK: finance namespace returned!"
    print("OK: finance namespace correctly excluded")

    print("\n== investigation (simulated agent) ==")
    MockBackend.instance().reset()
    cmd = Commander()
    incident = Commander.__init__ and None  # noqa
    from app.agents.schemas import Incident

    incident = Incident(trigger=IncidentTrigger(
        title="acmeshop_nightly_etl failed at transform", failed_task="transform"))

    types_seen = []
    async for ev in cmd.investigate(incident):
        types_seen.append(ev.type)
        tag = f"[{ev.actor}]"
        print(f"  {ev.type:18s} {tag:12s} {ev.title or ev.detail[:70]}")

    assert incident.status == IncidentStatus.AWAITING_APPROVAL, incident.status
    assert incident.root_cause is not None
    assert "chg_8f2a1c" in incident.root_cause.root_cause
    assert any(t == "vision" for t in types_seen), "vision step missing"
    assert any(t == "root_cause" for t in types_seen)
    print(f"\nroot cause: {incident.root_cause.root_cause}")
    print(f"confidence: {incident.root_cause.confidence}")
    print(f"proposed actions: {[a.action for a in incident.root_cause.proposed_actions]}")
    print(f"investigation duration: {incident.duration_ms:.1f} ms")

    print("\n== remediation (after approval) ==")
    async for ev in cmd.remediate(incident):
        print(f"  {ev.type:18s} {ev.title or ev.detail[:70]}")
    assert incident.status == IncidentStatus.RESOLVED, incident.status
    print("\nOK: incident RESOLVED, pipeline green after revert + rerun")

    print("\n== negative control: rerun without fix fails ==")
    mb = MockBackend.instance()
    mb.reset()
    r = mb.rerun_job(mb.job_id)
    assert r["ok"] is False, "rerun should fail before fixing config"
    mb.revert_config("chg_8f2a1c")
    r2 = mb.rerun_job(mb.job_id)
    assert r2["ok"] is True, "rerun should succeed after revert"
    print("OK: failure is deterministic; only the correct fix makes it green")

    print("\nALL SMOKE TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
