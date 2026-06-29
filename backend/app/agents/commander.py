"""Incident Commander: orchestrates triage -> specialists -> synthesis ->
hypothesis racing, then a gated remediation phase that verifies recovery,
auto-rolls-back on failure, and immunizes against recurrence.

Exposes two async event generators:
  - investigate(incident): autonomous, read-only investigation ending in a cited
    root cause, a parallel hypothesis race, and proposed actions (pausing at the
    human approval gate for any high-risk action).
  - remediate(incident): runs the approved actions, verifies recovery, rolls back
    and escalates if the rerun is not green, then files a preventive guardrail.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import time
from typing import Any, AsyncGenerator

from app.agents import prompts
from app.agents.schemas import (
    AgentEvent,
    CandidateFix,
    Evidence,
    Hypothesis,
    Incident,
    IncidentStatus,
    ProposedAction,
    ProposedGuardrail,
    RootCause,
)
from app.agents.specialists import SpecialistResult, run_specialist
from app.config import get_settings
from app.llm.cerebras_client import CerebrasClient
from app.pipeline.adapter import get_adapter
from app.tools import registry, remediation

SPECIALISTS = ["telemetry", "change", "knowledge"]


def _img_data_uri(path: str) -> str | None:
    try:
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        return f"data:image/png;base64,{b64}"
    except Exception:
        return None


def _active_scenario():
    from app.pipeline.mock_backend import MockBackend

    return MockBackend.instance().scenario


def _loads(content: str) -> dict[str, Any]:
    """Best-effort JSON extraction from a model response."""
    text = (content or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


class Commander:
    def __init__(self) -> None:
        self.client = CerebrasClient()
        self.settings = get_settings()

    # --------------------------------------------------------- investigate
    async def investigate(self, incident: Incident) -> AsyncGenerator[AgentEvent, None]:
        t0 = time.perf_counter()
        incident.status = IncidentStatus.INVESTIGATING
        incident.used_real_llm = not self.client.simulated
        incident.cost_per_min = _active_scenario().cost_per_min

        trig = incident.trigger
        yield AgentEvent(
            incident_id=incident.id, type="incident_opened", actor="system",
            title=trig.title,
            detail=f"job={trig.job_id} failed_task={trig.failed_task or 'unknown'} "
                   f"source={trig.source}",
            data={"engine": "cerebras:gemma-4-31b" if incident.used_real_llm else "simulated",
                  "scenario_id": incident.trigger.scenario_id or _active_scenario().id},
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

        # 5) Hypothesis racing: score N candidate fixes in parallel (Cerebras speed
        #    -> decision quality). Picks the safest fix predicted to go green.
        async for ev in self._race_hypotheses(incident, rc):
            yield ev

        # 6) Propose actions; gate high-risk ones.
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

    # ----------------------------------------------------- hypothesis racing
    async def _race_hypotheses(self, incident: Incident, rc: RootCause) -> AsyncGenerator[AgentEvent, None]:
        scenario = _active_scenario()
        specs = self._candidate_specs(scenario, rc)
        if not specs:
            return

        async def score(spec: dict[str, Any]) -> CandidateFix:
            if self.client.simulated:
                r = await self.client.chat_completion(
                    messages=[{"role": "user", "content": "score"}],
                    step=f"race:{spec['action']}", json_object=True)
            else:
                msgs = [
                    {"role": "system", "content": prompts.RACE_SCORING},
                    {"role": "user", "content": (
                        f"Root cause: {rc.root_cause}\n"
                        f"Candidate strategy: {spec['label']} -> action={spec['action']} "
                        f"args={json.dumps(spec['args'], default=str)}")},
                ]
                r = await self.client.chat_completion(
                    messages=msgs, reasoning_effort="low", step=f"race:{spec['action']}",
                    json_object=True)
            d = _loads(r.content)
            return CandidateFix(
                action=spec["action"], args=spec["args"], label=spec["label"],
                predicted_green=float(d.get("predicted_green", 0.0)),
                risk_tier=int(d.get("risk_tier", spec.get("risk_tier", 2))),
                confidence=float(d.get("confidence", 0.0)),
                predicted_outcome=d.get("predicted_outcome", ""),
            )

        # The whole point of Cerebras here: race all candidates concurrently.
        t0 = time.perf_counter()
        scored = await asyncio.gather(*[score(s) for s in specs])
        race_ms = (time.perf_counter() - t0) * 1000.0

        winner = max(scored, key=lambda c: (c.predicted_green, -c.risk_tier, c.confidence))
        winner.chosen = True
        incident.candidates = list(scored)

        detail = "  |  ".join(
            f"{c.label}: {round(c.predicted_green * 100)}% green" + (" [chosen]" if c.chosen else "")
            for c in scored
        )
        yield AgentEvent(
            incident_id=incident.id, type="hypothesis_race", actor="commander",
            title=f"Raced {len(scored)} candidate fixes in parallel", detail=detail,
            data={"candidates": [c.model_dump() for c in scored], "winner": winner.action,
                  "race_ms": round(race_ms, 1)},
        )

    def _candidate_specs(self, scenario, rc: RootCause) -> list[dict[str, Any]]:
        if self.client.simulated:
            return [{"action": c["action"], "args": dict(c["args"]),
                     "label": c.get("label", c["action"]), "risk_tier": c.get("risk_tier", 2)}
                    for c in scenario.sim["candidates"]]
        specs = [{"action": "rerun_job", "args": {"job_id": scenario.job_id},
                  "label": "Rerun as-is", "risk_tier": 2}]
        for a in rc.proposed_actions:
            if a.action in ("revert_config", "retry_with_params"):
                specs.append({"action": a.action, "args": dict(a.args or {}),
                              "label": a.action, "risk_tier": a.risk_tier})
        return specs

    # ----------------------------------------------------------- remediate
    async def remediate(self, incident: Incident) -> AsyncGenerator[AgentEvent, None]:
        incident.status = IncidentStatus.REMEDIATING
        rc = incident.root_cause
        if rc is None:
            yield AgentEvent(incident_id=incident.id, type="error", actor="system",
                             title="No root cause", detail="Cannot remediate without a root cause.")
            return

        rerun_ok = False
        did_rerun = False
        for action in rc.proposed_actions:
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
                did_rerun = True
                rerun_ok = bool(obs.get("ok"))
                yield AgentEvent(
                    incident_id=incident.id, type="verification", actor="commander",
                    title="Verifying recovery", detail=obs.get("message", ""),
                    data={"healthy": rerun_ok, "result": obs},
                )

        # Always verify by rerunning, even if the proposed plan omitted an explicit
        # rerun - we must confirm the fix actually restored the pipeline.
        if not did_rerun:
            obs = registry.dispatch("rerun_job", {"job_id": incident.trigger.job_id})
            rerun_ok = bool(obs.get("ok"))
            yield AgentEvent(
                incident_id=incident.id, type="verification", actor="commander",
                title="Verifying recovery", detail=obs.get("message", ""),
                data={"healthy": rerun_ok, "result": obs},
            )

        if rerun_ok:
            async for ev in self._resolve(incident, rc):
                yield ev
        else:
            async for ev in self._rollback_and_escalate(incident, rc):
                yield ev

        yield AgentEvent(incident_id=incident.id, type="done", actor="system",
                         title="Done", detail="", data={"status": incident.status.value})

    # ------------------------------------------------------ resolve + immunize
    async def _resolve(self, incident: Incident, rc: RootCause) -> AsyncGenerator[AgentEvent, None]:
        incident.status = IncidentStatus.RESOLVED
        incident.resolved_at = time.time()
        incident.mttr_seconds = max(0.0, incident.resolved_at - incident.created_at)
        mttr_min = incident.mttr_seconds / 60.0
        incident.dollars_avoided = round(
            max(0.0, incident.human_baseline_min - mttr_min) * incident.cost_per_min, 2)

        yield AgentEvent(
            incident_id=incident.id, type="summary", actor="commander",
            title="Post-incident summary",
            detail=(f"Incident resolved. Root cause: {rc.root_cause} Fix applied and the pipeline "
                    f"reran green. MTTR {mttr_min:.1f} min vs ~{incident.human_baseline_min:.0f} "
                    f"min human baseline; ~${incident.dollars_avoided:,.0f} downtime avoided."),
            data={"resolved": True, "mttr_seconds": round(incident.mttr_seconds, 1),
                  "mttr_min": round(mttr_min, 2), "cost_per_min": incident.cost_per_min,
                  "human_baseline_min": incident.human_baseline_min,
                  "dollars_avoided": incident.dollars_avoided},
        )

        # Immunize: generate + file a preventive guardrail for this failure class.
        async for ev in self._immunize(incident, rc):
            yield ev

    async def _immunize(self, incident: Incident, rc: RootCause) -> AsyncGenerator[AgentEvent, None]:
        if self.client.simulated:
            r = await self.client.chat_completion(
                messages=[{"role": "user", "content": "immunize"}], step="immunize", json_object=True)
        else:
            r = await self.client.chat_completion(
                messages=[{"role": "system", "content": prompts.IMMUNIZE},
                          {"role": "user", "content": f"Root cause: {rc.root_cause}"}],
                reasoning_effort="low", step="immunize", json_object=True)
        d = _loads(r.content)
        if not d.get("title"):
            return
        filed = remediation.file_guardrail(d.get("title", ""), d.get("policy", ""))
        guardrail = ProposedGuardrail(
            title=d.get("title", ""), policy=d.get("policy", ""),
            rationale=d.get("rationale", ""),
            artifact_kind=filed.get("artifact_kind", "pull_request"),
            artifact_id=filed.get("artifact_id"), artifact_url=filed.get("artifact_url"),
        )
        incident.guardrail = guardrail
        yield AgentEvent(
            incident_id=incident.id, type="immunize", actor="commander",
            title=f"Immunize: filed {guardrail.artifact_id}",
            detail=f"{guardrail.title} - {guardrail.policy}",
            data={"guardrail": guardrail.model_dump()},
        )

    # --------------------------------------------------- rollback + escalate
    async def _rollback_and_escalate(self, incident: Incident, rc: RootCause) -> AsyncGenerator[AgentEvent, None]:
        rb = remediation.rollback_changes()
        yield AgentEvent(
            incident_id=incident.id, type="rollback", actor="commander",
            title="Auto-rollback: rerun did not go green",
            detail=("The applied fix did not restore the pipeline, so CereMind reverted its own "
                    f"change. {rb.get('message', '')}"),
            data={"rollback": rb},
        )
        ticket = remediation.create_ticket(
            title=f"[CereMind] Escalation: {incident.trigger.title}",
            body=f"Auto-remediation failed and was rolled back. Root cause: {rc.root_cause}")
        remediation.post_to_slack(
            channel="#incidents",
            message=f"CereMind rolled back its fix for {incident.trigger.job_id} and escalated "
                    f"to on-call ({ticket.get('ticket_id')}).")
        incident.status = IncidentStatus.FAILED
        yield AgentEvent(
            incident_id=incident.id, type="summary", actor="commander",
            title="Rolled back and escalated",
            detail=(f"Remediation did not verify green; CereMind rolled back its change and escalated "
                    f"to on-call ({ticket.get('ticket_id')}) with the full audit trail. "
                    f"Root cause stands: {rc.root_cause}"),
            data={"resolved": False, "rolled_back": True, "ticket": ticket.get("ticket_id")},
        )

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
    data = _loads(content)
    if not data:
        return RootCause(root_cause=(content or "")[:300] or "Unparseable synthesis output",
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
