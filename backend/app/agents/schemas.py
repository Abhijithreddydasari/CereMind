"""Pydantic models shared across the agent, API, and audit layers."""
from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _now() -> float:
    return time.time()


# --------------------------------------------------------------------------- #
# Risk tiers for remediation actions
# --------------------------------------------------------------------------- #
class RiskTier(int, Enum):
    READ_ONLY = 0           # investigation, always autonomous
    LOW_REVERSIBLE = 1      # auto-with-notice
    HIGH = 2                # requires human approval


# --------------------------------------------------------------------------- #
# Evidence + root cause
# --------------------------------------------------------------------------- #
EvidenceSource = Literal["job_log", "metrics", "config_change", "runbook", "incident", "vision"]


class Evidence(BaseModel):
    source: EvidenceSource
    ref: str = Field(..., description="Stable reference id, e.g. run id, change id, doc id")
    detail: str = Field(..., description="Human-readable supporting detail")


class Hypothesis(BaseModel):
    claim: str
    likelihood: float = Field(0.0, ge=0.0, le=1.0)
    evidence: list[Evidence] = Field(default_factory=list)


class ProposedAction(BaseModel):
    id: str = Field(default_factory=lambda: _id("act"))
    action: str
    args: dict[str, Any] = Field(default_factory=dict)
    risk_tier: int = RiskTier.HIGH.value
    rationale: str = ""
    status: Literal["proposed", "approved", "rejected", "executed", "failed"] = "proposed"
    result: Optional[str] = None


class RootCause(BaseModel):
    root_cause: str
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    proposed_actions: list[ProposedAction] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Hypothesis racing: N candidate fixes scored in parallel (speed -> decisions)
# --------------------------------------------------------------------------- #
class CandidateFix(BaseModel):
    action: str
    args: dict[str, Any] = Field(default_factory=dict)
    label: str = ""
    predicted_green: float = Field(0.0, ge=0.0, le=1.0)
    risk_tier: int = RiskTier.HIGH.value
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    predicted_outcome: str = ""
    chosen: bool = False


# --------------------------------------------------------------------------- #
# Immunize: a preventive guardrail filed after resolution
# --------------------------------------------------------------------------- #
class ProposedGuardrail(BaseModel):
    title: str
    policy: str
    rationale: str = ""
    artifact_kind: str = "pull_request"
    artifact_id: Optional[str] = None
    artifact_url: Optional[str] = None


# --------------------------------------------------------------------------- #
# Streaming events (sent to the war-room console over SSE)
# --------------------------------------------------------------------------- #
EventType = Literal[
    "incident_opened",
    "vision",
    "thought",
    "specialist_start",
    "specialist_done",
    "tool_call",
    "observation",
    "root_cause",
    "hypothesis_race",
    "action_proposed",
    "awaiting_approval",
    "action_executed",
    "verification",
    "rollback",
    "immunize",
    "summary",
    "error",
    "done",
]


class AgentEvent(BaseModel):
    id: str = Field(default_factory=lambda: _id("evt"))
    incident_id: str
    ts: float = Field(default_factory=_now)
    type: EventType
    # Free-form, type-dependent payload (kept loose so the UI can render richly).
    actor: str = "commander"           # commander | telemetry | change | knowledge | system
    title: str = ""
    detail: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Incident
# --------------------------------------------------------------------------- #
class IncidentTrigger(BaseModel):
    """Payload that opens an incident (alert webhook or manual)."""
    source: Literal["webhook", "manual"] = "webhook"
    title: str = "Job failed"
    summary: str = ""
    job_id: str = "acmeshop_nightly_etl"
    failed_task: Optional[str] = None
    # Which incident pack to investigate (see app.pipeline.scenarios).
    scenario_id: Optional[str] = None
    # Optional base64 data URI of an attached dashboard/DAG snapshot.
    snapshot_data_uri: Optional[str] = None
    # If true, attach the seeded DAG snapshot automatically (alert-carried image).
    attach_seeded_snapshot: bool = True


class IncidentStatus(str, Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    AWAITING_APPROVAL = "awaiting_approval"
    REMEDIATING = "remediating"
    RESOLVED = "resolved"
    FAILED = "failed"


class Incident(BaseModel):
    id: str = Field(default_factory=lambda: _id("inc"))
    created_at: float = Field(default_factory=_now)
    trigger: IncidentTrigger
    status: IncidentStatus = IncidentStatus.OPEN
    root_cause: Optional[RootCause] = None
    candidates: list[CandidateFix] = Field(default_factory=list)
    guardrail: Optional[ProposedGuardrail] = None
    events: list[AgentEvent] = Field(default_factory=list)
    used_real_llm: bool = False
    duration_ms: Optional[float] = None
    resolved_at: Optional[float] = None
    # Business-impact meter.
    cost_per_min: float = 0.0
    human_baseline_min: float = 22.0
    mttr_seconds: Optional[float] = None
    dollars_avoided: Optional[float] = None
