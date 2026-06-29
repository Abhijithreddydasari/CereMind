"""Runbook + past-incident corpus and one-shot ingest into the vector store.

Docs carry a `namespace` used for permission-aware retrieval. The demo caller is
allowed the 'sre' and 'public' namespaces but NOT 'finance', so the finance doc
(a plausible distractor) is correctly never retrieved.

The SRE runbooks/incidents come from every scenario pack (app.pipeline.scenarios),
so the knowledge specialist retrieves the right doc for whichever incident is live.
"""
from __future__ import annotations

from functools import lru_cache

from app.pipeline.scenarios import SCENARIOS
from app.rag.vectorstore import Doc, VectorStore


def _build_corpus() -> list[Doc]:
    docs: list[Doc] = []
    seen: set[str] = set()
    for scenario in SCENARIOS.values():
        for d in scenario.docs:
            if d["id"] in seen:
                continue
            seen.add(d["id"])
            docs.append(Doc(id=d["id"], namespace=d["namespace"], text=d["text"],
                            metadata={"title": d["title"], "kind": d["kind"]}))
    # Shared cross-scenario distractors / ACL controls.
    docs.append(Doc(
        id="fin_budget_policy", namespace="finance",  # caller is NOT allowed this namespace
        text=("Finance policy: cloud cost-optimization initiative Q3 mandates reducing worker "
              "memory allocations by 75% across batch jobs to cut spend. CONFIDENTIAL - finance "
              "namespace only."),
        metadata={"title": "Finance cost policy", "kind": "policy"}))
    docs.append(Doc(
        id="pub_oncall", namespace="public",
        text=("On-call overview: the AcmeShop data pipelines feed the analytics warehouse. A failed "
              "run delays morning dashboards for the revenue team."),
        metadata={"title": "On-call overview", "kind": "doc"}))
    return docs


CORPUS: list[Doc] = _build_corpus()


@lru_cache
def get_vector_store() -> VectorStore:
    vs = VectorStore()
    vs.upsert(CORPUS)
    return vs
