"""End-to-end backend smoke test (runs against the simulated agent, no API key).

Validates, for every incident scenario: imports, snapshot generation, embeddings +
permission-aware RAG, the full investigation event stream, hypothesis racing, the
approval gate, gated remediation with recovery verification, and the Immunize step.
Also exercises the negative auto-rollback path.
"""
from __future__ import annotations

import asyncio
import sys

from app.agents.commander import Commander
from app.agents.schemas import Incident, IncidentStatus, IncidentTrigger
from app.pipeline.mock_backend import MockBackend
from app.pipeline.scenarios import SCENARIOS
from app.rag.embeddings import get_embedder
from app.rag.ingest import get_vector_store
from app.tools import knowledge


def _make_incident(scenario) -> Incident:
    return Incident(trigger=IncidentTrigger(
        title=scenario.title, job_id=scenario.job_id, failed_task=scenario.failed_task,
        summary=scenario.summary, scenario_id=scenario.id))


async def _run_scenario(scenario) -> None:
    print(f"\n===== scenario: {scenario.id} ({scenario.failed_task}) =====")
    mb = MockBackend.instance()
    mb.load_scenario(scenario.id)
    cmd = Commander()
    incident = _make_incident(scenario)

    types_seen: list[str] = []
    async for ev in cmd.investigate(incident):
        types_seen.append(ev.type)
        print(f"  {ev.type:18s} [{ev.actor:10s}] {(ev.title or ev.detail)[:74]}")

    assert incident.status == IncidentStatus.AWAITING_APPROVAL, incident.status
    assert incident.root_cause is not None
    assert scenario.culprit_change_id in incident.root_cause.root_cause, "culprit not in root cause"
    assert "vision" in types_seen, "vision step missing"
    assert "root_cause" in types_seen
    assert "hypothesis_race" in types_seen, "hypothesis race missing"
    assert incident.candidates, "no candidates scored"
    winner = next((c for c in incident.candidates if c.chosen), None)
    assert winner is not None and winner.action == "revert_config", \
        f"expected revert_config to win, got {winner.action if winner else None}"
    print(f"  -> winner: {winner.label} ({round(winner.predicted_green*100)}% green)")

    async for ev in cmd.remediate(incident):
        print(f"  {ev.type:18s} [{ev.actor:10s}] {(ev.title or ev.detail)[:74]}")
    assert incident.status == IncidentStatus.RESOLVED, incident.status
    assert incident.guardrail is not None, "Immunize did not file a guardrail"
    assert incident.guardrail.artifact_id, "guardrail has no artifact id"
    assert incident.mttr_seconds is not None and incident.dollars_avoided is not None
    print(f"  -> RESOLVED; guardrail {incident.guardrail.artifact_id}: {incident.guardrail.title}")
    print(f"  -> MTTR {incident.mttr_seconds:.2f}s; ~${incident.dollars_avoided:,.0f} avoided")


async def _run_rollback(scenario) -> None:
    print(f"\n===== negative path (auto-rollback): {scenario.id} =====")
    mb = MockBackend.instance()
    mb.load_scenario(scenario.id)
    cmd = Commander()
    incident = _make_incident(scenario)
    async for _ in cmd.investigate(incident):
        pass
    assert incident.status == IncidentStatus.AWAITING_APPROVAL
    # Force the rerun to NOT go green even after the fix, to exercise rollback.
    mb.force_fail_rerun = True
    saw_rollback = False
    async for ev in cmd.remediate(incident):
        if ev.type == "rollback":
            saw_rollback = True
            print(f"  rollback: {ev.detail[:90]}")
    assert saw_rollback, "rollback event not emitted"
    assert incident.status == IncidentStatus.FAILED, incident.status
    assert scenario.culprit_change_id not in mb.reverted_changes, "rollback did not undo the revert"
    print("  -> rolled back + escalated; backend restored to pre-remediation state")


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

    for scenario in SCENARIOS.values():
        await _run_scenario(scenario)

    await _run_rollback(SCENARIOS["oom_memory_cut"])

    print("\nALL SMOKE TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
