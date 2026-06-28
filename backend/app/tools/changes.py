"""Change specialist tools: recent config changes and diffs."""
from __future__ import annotations

from typing import Any

from app.pipeline.adapter import get_adapter


def list_recent_config_changes(limit: int = 5) -> dict[str, Any]:
    return {"changes": get_adapter().list_recent_config_changes(limit=limit)}


def config_diff(change_id: str) -> dict[str, Any]:
    return get_adapter().config_diff(change_id=change_id)
