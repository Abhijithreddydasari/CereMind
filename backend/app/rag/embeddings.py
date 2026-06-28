"""Embeddings with graceful degradation.

Tier 1: EmbeddingGemma (google/embeddinggemma-300m) via sentence-transformers,
        using its task-specific prompts (query vs document) per the model card.
Tier 2: a generic sentence-transformers model, if EmbeddingGemma is unavailable.
Tier 3: a deterministic hashing vectorizer (no ML deps) so the app always runs.

The active backend is reported so the UI/README can be honest about it.
"""
from __future__ import annotations

import hashlib
import math
import re
from functools import lru_cache
from typing import Literal

import numpy as np

from app.config import get_settings

TaskType = Literal["query", "document"]

_HASH_DIM = 512


class Embedder:
    def __init__(self) -> None:
        self.backend = "hashing"
        self.dim = _HASH_DIM
        self._model = None
        self._load()

    def _load(self) -> None:
        settings = get_settings()
        pref = settings.embedding_backend
        if pref == "hashing":
            return
        # Try EmbeddingGemma, then a generic ST model.
        candidates = []
        if pref in ("auto", "embeddinggemma"):
            candidates.append(settings.embedding_gemma_model)
        if pref == "auto":
            candidates.append("sentence-transformers/all-MiniLM-L6-v2")
        for name in candidates:
            try:
                from sentence_transformers import SentenceTransformer  # type: ignore

                kwargs = {}
                if settings.huggingface_token:
                    kwargs["token"] = settings.huggingface_token
                self._model = SentenceTransformer(name, **kwargs)
                self.dim = int(self._model.get_sentence_embedding_dimension())
                self.backend = "embeddinggemma" if "embeddinggemma" in name else "sentence-transformers"
                self._model_name = name
                return
            except Exception:
                continue
        # else stay on hashing

    # --- public API ---------------------------------------------------------
    def embed(self, texts: list[str], task: TaskType = "document") -> np.ndarray:
        if self._model is not None:
            return self._embed_st(texts, task)
        return np.vstack([self._hash_vec(t) for t in texts])

    def _embed_st(self, texts: list[str], task: TaskType) -> np.ndarray:
        # EmbeddingGemma uses task-prefixed prompts; emulate per the model card.
        if self.backend == "embeddinggemma":
            if task == "query":
                texts = [f"task: search result | query: {t}" for t in texts]
            else:
                texts = [f"title: none | text: {t}" for t in texts]
        vecs = self._model.encode(texts, normalize_embeddings=True)
        return np.asarray(vecs, dtype=np.float32)

    def _hash_vec(self, text: str) -> np.ndarray:
        """Deterministic bag-of-hashed-tokens vector, L2-normalized."""
        vec = np.zeros(self.dim, dtype=np.float32)
        tokens = re.findall(r"[a-z0-9]+", text.lower())
        for tok in tokens:
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
            idx = h % self.dim
            sign = 1.0 if (h >> 8) & 1 else -1.0
            vec[idx] += sign
        norm = math.sqrt(float(np.dot(vec, vec)))
        if norm > 0:
            vec /= norm
        return vec


@lru_cache
def get_embedder() -> Embedder:
    return Embedder()
