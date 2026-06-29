"""Incident Commander: orchestrates triage -> specialists -> synthesis, then a
gated remediation + verification phase.

Exposes two async event generators:
  - investigate(incident): autonomous, read-only investigation ending in a cited
    root cause and proposed actions (pausing at the human approval gate for any
    high-risk action).
  - remediate(incident): runs the approved actions, verifies recovery, and writes
    the post-mortem summary.
"""
from __future__ import annotations

import base64
import json
import os
import time
from typing import Any, AsyncGenerator

from app.agents import prompts
from app.agents.schemas import (
    AgentEvent,
    Evidence,
    Hypothesis,
    Incident,
    IncidentStatus,
    ProposedAction,
    RootCause,
)
from app.agents.specialists import SpecialistResult, run_specialist
from app.config import get_settings
from app.llm.cerebras_client import CerebrasClient
from app.pipeline.adapter import get_adapter
from app.tools import registry

SPECIALISTS = ["telemetry", "change", "knowledge"]


def _img_data_uri(path: str) -> str | None:
    try:
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        return f"data:image/png;base64,{b64}"
    except Exception:
        return None


class Commander:
    def __init__(self) -> None:
        self.client = CerebrasClient()
        self.settings = get_settings()

    # --------------------------------------------------------- investigate
    async def investigate(self, incident: Incident) -> AsyncGenerator[AgentEvent, None]:
        t0 = time.perf_counter()
        incident.status = IncidentStatus.INVESTIGATING
        incident.used_real_llm = not self.client.simulated

        trig = incident.trigger
        yield AgentEvent(
            incident_id=incident.id, type="incident_opened", actor="system",
            title=trig.title,
            detail=f"job={trig.job_id} failed_task={trig.failed_task or 'unknown'} "
                   f"source={trig.source}",
            data={"engine": "cerebras:gemma-4-31b" if incident.used_real_llm else "simulated"},
        )

        # 1) Multimodal perception (vision) on the alert's snapshot.
        vision_summary = ""
        snapshot = trig.snapshot_data_uri
        if snapshot is None and trig.attach_seeded_snapshot:
            path = get_adapter().get_dag_snapshot_path()
            if os.path.exists(path):
                snapshot = _img_data_uri(path)
        if snapshot:
            messages = [
                {"role": "system", "content": "You read pipeline dashboard/DAG snapshots."},
                {"role": "user", "content": [
                    {"type": "text", "text": "What does this pipeline snapshot show? Be specific "
                     "about which stage failed and any resource limits visible."},
                    {"type": "image_url", "image_url": {"url": snapshot}},
                ]},
            ]
            res = await self.client.chat_completion(
                messages=messages, reasoning_effort="low", step="vision",
            )
            vision_summary = res.content
            yield AgentEvent(incident_id=incident.id, type="vision", actor="commander",
                             title="Read alert snapshot (Gemma 4 vision)", detail=vision_summary,
                             data={"has_image": True})

        # 2) Triage plan (high reasoning).
        context = (
            f"Alert: {trig.title}\nJob: {trig.job_id}\nFailed task: "
            f"{trig.failed_task or 'unknown'}\nSummary: {trig.summary or '(none)'}\n"
            f"Vision: {vision_summary or '(no snapshot)'}"
        )
        triage = await self.client.chat_completion(
            messages=[{"role": "system", "content": prompts.COMMANDER_TRIAGE},
                      {"role": "user", "content": context}],
            reasoning_effort="high", step="triage",
        )
        yield AgentEvent(incident_id=incident.id, type="thought", actor="commander",
                         title="Triage plan", detail=triage.content)

        # 3) Specialists.
        findings: list[SpecialistResult] = []
        all_observations: list[dict[str, Any]] = []
        spec_context = context + "\n\nInvestigate now using your tools."
        for spec in SPECIALISTS:
            async for event, result in run_specialist(self.client, incident.id, spec, spec_context):
                yield event
                if result is not None:
                    findings.append(result)
                    all_observations.extend(result.observations)

        # 4) Synthesis -> structured, cited root cause (high reasoning).
        findings_text = "\n".join(f"[{f.specialist}] {f.finding}" for f in findings)
        obs_text = "\n".join(
            f"- {o['tool']}({json.dumps(o['args'], default=str)}) -> "
            f"{json.dumps(o['result'], default=str)[:400]}"
            for o in all_observations
        )
        synth = await self.client.chat_completion(
            messages=[
                {"role": "system", "content": prompts.SYNTHESIS},
                {"role": "user", "content": f"Vision:\n{vision_summary}\n\nSpecialist findings:\n"
                                            f"{findings_text}\n\nObservations:\n{obs_text}"},
            ],
            reasoning_effort="high", step="synthesis", json_object=True,
        )
        rc = _parse_root_cause(synth.content)
        incident.root_cause = rc

        yield AgentEvent(incident_id=incident.id, type="root_cause", actor="commander",
                         title="Root cause identified", detail=rc.root_cause,
                         data=rc.model_dump())

        # 5) Propose actions; gate high-risk ones.
        needs_approval = False
        for action in rc.proposed_actions:
            yield AgentEvent(incident_id=incident.id, type="action_proposed", actor="commander",
                             title=action.action, detail=action.rationale,
                             data=action.model_dump())
            if action.risk_tier >= 2:
                needs_approval = True

        incident.duration_ms = (time.perf_counter() - t0) * 1000.0

        if needs_approval:
            incident.status = IncidentStatus.AWAITING_APPROVAL
            yield AgentEvent(
                incident_id=incident.id, type="awaiting_approval", actor="commander",
                title="Awaiting human approval",
                detail="High-risk remediation proposed. Approve to let CereMind apply the fix "
                       "and rerun the job.",
                data={"investigation_ms": round(incident.duration_ms, 1)},
            )
        else:
            async for ev in self.remediate(incident):
                yield ev

    # ----------------------------------------------------------- remediate
    async def remediate(self, incident: Incident) -> AsyncGenerator[AgentEvent, None]:
        incident.status = IncidentStatus.REMEDIATING
        rc = incident.root_cause
        if rc is None:
            yield AgentEvent(incident_id=incident.id, type="error", actor="system",
                             title="No root cause", detail="Cannot remediate without a root cause.")
            return

        rerun_ok = False
        for action in rc.proposed_actions:
            # Enrich model-proposed args with incident context so an omitted
            # job_id (the model isn't constrained on synthesis output) still works.
            args = dict(action.args or {})
            if action.action in ("rerun_job", "retry_with_params") and not (
                args.get("job_id") or args.get("dag_id") or args.get("job")
            ):
                args["job_id"] = incident.trigger.job_id
            action.args = args
            obs = registry.dispatch(action.action, args)
            action.status = "executed" if obs.get("ok", True) and "error" not in obs else "failed"
            action.result = obs.get("message") or json.dumps(obs, default=str)[:300]
            yield AgentEvent(
                incident_id=incident.id, type="action_executed", actor="commander",
                title=f"Executed {action.action}", detail=action.result,
                data={"action": action.model_dump(), "result": obs},
            )
            if action.action == "rerun_job":
                rerun_ok = bool(obs.get("ok"))
                yield AgentEvent(
                    incident_id=incident.id, type="verification", actor="commander",
                    title="Verifying recovery",
                    detail=obs.get("message", ""),
                    data={"healthy": rerun_ok, "result": obs},
                )

        incident.status = IncidentStatus.RESOLVED if rerun_ok else IncidentStatus.FAILED
        summary = (
            f"Incident resolved. Root cause: {rc.root_cause} "
            f"Fix applied and the nightly ETL reran green."
            if rerun_ok else
            f"Remediation incomplete. Root cause: {rc.root_cause} Manual follow-up required."
        )
        yield AgentEvent(incident_id=incident.id, type="summary", actor="commander",
                         title="Post-incident summary", detail=summary,
                         data={"resolved": rerun_ok})
        yield AgentEvent(incident_id=incident.id, type="done", actor="system",
                         title="Done", detail="", data={"status": incident.status.value})

    async def reject(self, incident: Incident) -> AsyncGenerator[AgentEvent, None]:
        incident.status = IncidentStatus.FAILED
        yield AgentEvent(incident_id=incident.id, type="summary", actor="system",
                         title="Remediation rejected",
                         detail="Operator rejected the proposed fix. Handed back to the on-call "
                                "engineer with the full investigation and audit trail.",
                         data={"resolved": False})
        yield AgentEvent(incident_id=incident.id, type="done", actor="system", title="Done",
                         data={"status": incident.status.value})


def _parse_root_cause(content: str) -> RootCause:
    """Robustly parse the synthesis JSON into a RootCause."""
    text = (content or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    # Extract the outermost JSON object if surrounded by prose.
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return RootCause(root_cause=content[:300] or "Unparseable synthesis output",
                         confidence=0.3)
    actions = [ProposedAction(**a) for a in data.get("proposed_actions", [])]
    hyps = []
    for h in data.get("hypotheses", []):
        ev = [Evidence(**e) for e in h.get("evidence", [])]
        hyps.append(Hypothesis(claim=h.get("claim", ""), likelihood=float(h.get("likelihood", 0.0)),
                               evidence=ev))
    return RootCause(
        root_cause=data.get("root_cause", ""),
        confidence=float(data.get("confidence", 0.0)),
        hypotheses=hyps,
        proposed_actions=actions,
    )
