"""Central configuration, loaded from environment / .env."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root = two levels up from this file (backend/app/config.py -> repo root).
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Cerebras
    cerebras_api_key: str = ""
    cerebras_base_url: str = "https://api.cerebras.ai/v1"
    cerebras_model: str = "gemma-4-31b"
    # Force the deterministic simulated agent even when a key is present
    # (useful for offline/deterministic demo recordings and tests).
    force_simulated: bool = False

    # GPU baseline for the speed race (e.g. Gemma 4 31B IT on Modal Endpoints).
    baseline_base_url: str = ""
    baseline_api_key: str = ""
    baseline_model: str = ""
    baseline_label: str = "Gemma 4 31B IT - GPU baseline (representative)"
    baseline_sim_tps: float = 55.0

    # Embeddings
    embedding_backend: str = "auto"  # auto | embeddinggemma | hashing
    embedding_gemma_model: str = "google/embeddinggemma-300m"
    huggingface_token: str = ""

    # Pipeline backend
    pipeline_backend: str = "mock"  # mock | airflow
    airflow_base_url: str = "http://localhost:8080/api/v1"
    airflow_username: str = "airflow"
    airflow_password: str = "airflow"

    # Misc
    default_reasoning_effort: str = "medium"

    @property
    def has_cerebras(self) -> bool:
        return bool(self.cerebras_api_key.strip())

    @property
    def has_baseline(self) -> bool:
        return bool(self.baseline_base_url.strip() and self.baseline_model.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
