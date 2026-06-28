"""Knowledge specialist tools: permission-aware runbook + past-incident search."""
from __future__ import annotations

from typing import Any

from app.rag.ingest import get_vector_store

# The demo caller's allowed namespaces. NOTE: 'finance' is intentionally excluded
# so the confidential finance policy is never retrieved (permission-aware RAG).
ALLOWED_NAMESPACES = ["sre", "public"]


def query_runbook(query: str, top_k: int = 3) -> dict[str, Any]:
    hits = get_vector_store().search(query, allowed_namespaces=ALLOWED_NAMESPACES, top_k=top_k)
    return {"results": [h for h in hits if h["metadata"].get("kind") in ("runbook", "doc", "policy")]
            or hits}


def find_similar_failures(query: str, top_k: int = 3) -> dict[str, Any]:
    hits = get_vector_store().search(query, allowed_namespaces=ALLOWED_NAMESPACES, top_k=top_k)
    incidents = [h for h in hits if h["metadata"].get("kind") == "incident"]
    return {"results": incidents or hits}
