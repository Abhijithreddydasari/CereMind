"""Append-only audit log.

Every agent thought, tool call, observation, proposed action, approval decision,
and execution result is appended as one JSON line. This is the governance/trust
surface required for production incident response, and it doubles as the data
the post-mortem is generated from.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()
_LOG_PATH = Path(__file__).resolve().parent / "audit.log.jsonl"


def record(incident_id: str, kind: str, payload: dict[str, Any]) -> None:
    entry = {"ts": time.time(), "incident_id": incident_id, "kind": kind, "payload": payload}
    line = json.dumps(entry, default=str)
    with _LOCK:
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def read_for_incident(incident_id: str) -> list[dict[str, Any]]:
    if not _LOG_PATH.exists():
        return []
    out: list[dict[str, Any]] = []
    with open(_LOG_PATH, "r", encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("incident_id") == incident_id:
                out.append(entry)
    return out
