"""Permission-aware vector store.

Uses Qdrant in local in-memory mode when available; otherwise a small numpy
cosine store. Either way, retrieval is permission-aware: every chunk carries a
`namespace` and queries filter to the caller's allowed namespaces. That ACL
filter is the difference between toy RAG and enterprise RAG.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from app.rag.embeddings import get_embedder


@dataclass
class Doc:
    id: str
    text: str
    namespace: str
    metadata: dict[str, Any] = field(default_factory=dict)


class _NumpyStore:
    """Fallback cosine store."""

    def __init__(self, dim: int) -> None:
        self.dim = dim
        self._vecs: list[np.ndarray] = []
        self._docs: list[Doc] = []

    def upsert(self, docs: list[Doc], vecs: np.ndarray) -> None:
        for d, v in zip(docs, vecs):
            self._docs.append(d)
            self._vecs.append(v)

    def search(self, qv: np.ndarray, allowed: Optional[set[str]], top_k: int) -> list[dict[str, Any]]:
        if not self._vecs:
            return []
        mat = np.vstack(self._vecs)
        sims = mat @ qv
        order = np.argsort(-sims)
        out = []
        for i in order:
            d = self._docs[i]
            if allowed is not None and d.namespace not in allowed:
                continue
            out.append({"id": d.id, "score": float(sims[i]), "text": d.text,
                        "namespace": d.namespace, "metadata": d.metadata})
            if len(out) >= top_k:
                break
        return out


class VectorStore:
    def __init__(self) -> None:
        self.embedder = get_embedder()
        self.dim = self.embedder.dim
        self.backend = "qdrant"
        self._qdrant = None
        self._collection = "ceremind"
        self._np: Optional[_NumpyStore] = None
        self._init_backend()

    def _init_backend(self) -> None:
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams

            self._qdrant = QdrantClient(location=":memory:")
            self._qdrant.recreate_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(size=self.dim, distance=Distance.COSINE),
            )
        except Exception:
            self.backend = "numpy"
            self._np = _NumpyStore(self.dim)

    def upsert(self, docs: list[Doc]) -> None:
        if not docs:
            return
        vecs = self.embedder.embed([d.text for d in docs], task="document")
        if self._qdrant is not None:
            from qdrant_client.models import PointStruct

            points = [
                PointStruct(
                    id=i,
                    vector=vecs[i].tolist(),
                    payload={"doc_id": d.id, "text": d.text, "namespace": d.namespace,
                             "metadata": d.metadata},
                )
                for i, d in enumerate(docs)
            ]
            self._qdrant.upsert(collection_name=self._collection, points=points)
        else:
            assert self._np is not None
            self._np.upsert(docs, vecs)

    def search(
        self,
        query: str,
        allowed_namespaces: Optional[list[str]] = None,
        top_k: int = 4,
    ) -> list[dict[str, Any]]:
        qv = self.embedder.embed([query], task="query")[0]
        allowed = set(allowed_namespaces) if allowed_namespaces is not None else None
        if self._qdrant is not None:
            from qdrant_client.models import FieldCondition, Filter, MatchAny

            flt = None
            if allowed is not None:
                flt = Filter(must=[FieldCondition(key="namespace",
                                                  match=MatchAny(any=list(allowed)))])
            res = self._qdrant.search(
                collection_name=self._collection,
                query_vector=qv.tolist(),
                query_filter=flt,
                limit=top_k,
            )
            return [
                {"id": r.payload["doc_id"], "score": float(r.score),
                 "text": r.payload["text"], "namespace": r.payload["namespace"],
                 "metadata": r.payload.get("metadata", {})}
                for r in res
            ]
        assert self._np is not None
        return self._np.search(qv, allowed, top_k)
