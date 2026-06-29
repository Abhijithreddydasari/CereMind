import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  approve,
  fireAlert,
  reject,
  startManual,
  streamIncident,
  type AgentEvent,
  type AppConfig,
  type CandidateFix,
  type Guardrail,
  type ProposedAction,
  type RootCause,
} from "../lib/api";
import AgentTimeline from "./AgentTimeline";
import RootCauseCard from "./RootCauseCard";
import RemediationPanel from "./RemediationPanel";
import ScreenshotDrop from "./ScreenshotDrop";
import { Alert, Bolt, Check, Play, Shield } from "./icons";

type Phase = "idle" | "investigating" | "awaiting" | "remediating" | "resolved" | "failed";

interface Impact {
  mttr_min: number;
  dollars_avoided: number;
  human_baseline_min: number;
}

const PHASE_META: Record<Phase, { label: string; cls: string; dot: string }> = {
  idle: { label: "Idle", cls: "border-edge bg-elevated/60 text-muted", dot: "bg-muted" },
  investigating: {
    label: "Investigating",
    cls: "border-cyan/30 bg-cyan/10 text-cyan",
    dot: "bg-cyan",
  },
  awaiting: {
    label: "Awaiting approval",
    cls: "border-warn/30 bg-warn/10 text-warn",
    dot: "bg-warn",
  },
  remediating: {
    label: "Remediating",
    cls: "border-accent/30 bg-accent/10 text-accent2",
    dot: "bg-accent2",
  },
  resolved: {
    label: "Resolved - green",
    cls: "border-ok/30 bg-ok/10 text-ok",
    dot: "bg-ok",
  },
  failed: { label: "Needs attention", cls: "border-bad/30 bg-bad/10 text-bad", dot: "bg-bad" },
};

export default function IncidentConsole({ cfg }: { cfg: AppConfig | null }) {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [rootCause, setRootCause] = useState<RootCause | null>(null);
  const [actions, setActions] = useState<ProposedAction[]>([]);
  const [candidates, setCandidates] = useState<CandidateFix[]>([]);
  const [guardrail, setGuardrail] = useState<Guardrail | null>(null);
  const [impact, setImpact] = useState<Impact | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [incidentId, setIncidentId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [elapsedMs, setElapsedMs] = useState<number | null>(null);
  const [scenarioId, setScenarioId] = useState<string>("");
  const manualSnapshot = useRef<string | undefined>(undefined);
  const closeRef = useRef<null | (() => void)>(null);

  const scenarios = cfg?.scenarios ?? [];
  useEffect(() => {
    if (!scenarioId && scenarios.length) setScenarioId(scenarios[0].id);
  }, [scenarios, scenarioId]);

  const onEvent = useCallback((e: AgentEvent) => {
    setEvents((prev) => [...prev, e]);
    switch (e.type) {
      case "root_cause":
        setRootCause(e.data as RootCause);
        setActions(((e.data as RootCause).proposed_actions ?? []).map((a) => ({ ...a })));
        break;
      case "hypothesis_race":
        setCandidates((e.data?.candidates as CandidateFix[]) ?? []);
        break;
      case "immunize":
        setGuardrail((e.data?.guardrail as Guardrail) ?? null);
        break;
      case "awaiting_approval":
        setPhase("awaiting");
        if (typeof e.data?.investigation_ms === "number") setElapsedMs(e.data.investigation_ms);
        break;
      case "action_executed": {
        const updated = e.data?.action as ProposedAction | undefined;
        if (updated)
          setActions((prev) =>
            prev.map((a) => (a.action === updated.action ? { ...a, ...updated } : a))
          );
        setPhase("remediating");
        break;
      }
      case "rollback":
        setPhase("remediating");
        break;
      case "summary":
        setPhase(e.data?.resolved ? "resolved" : "failed");
        if (e.data?.resolved && typeof e.data?.dollars_avoided === "number")
          setImpact({
            mttr_min: e.data.mttr_min,
            dollars_avoided: e.data.dollars_avoided,
            human_baseline_min: e.data.human_baseline_min,
          });
        break;
      case "error":
        setPhase("failed");
        break;
      default:
        setPhase((p) => (p === "idle" || p === "investigating" ? "investigating" : p));
    }
  }, []);

  function reset() {
    closeRef.current?.();
    setEvents([]);
    setRootCause(null);
    setActions([]);
    setCandidates([]);
    setGuardrail(null);
    setImpact(null);
    setElapsedMs(null);
    setPhase("idle");
    setIncidentId(null);
  }

  async function trigger(kind: "alert" | "manual") {
    reset();
    setBusy(true);
    setPhase("investigating");
    try {
      const res =
        kind === "alert"
          ? await fireAlert(scenarioId || undefined)
          : await startManual(manualSnapshot.current, scenarioId || undefined);
      setIncidentId(res.incident_id);
      closeRef.current = streamIncident(res.incident_id, onEvent);
    } finally {
      setBusy(false);
    }
  }

  async function doApprove() {
    if (!incidentId) return;
    setBusy(true);
    setPhase("remediating");
    try {
      await approve(incidentId);
    } finally {
      setBusy(false);
    }
  }
  async function doReject() {
    if (!incidentId) return;
    setBusy(true);
    try {
      await reject(incidentId);
    } finally {
      setBusy(false);
    }
  }

  const meta = PHASE_META[phase];
  const engine = useMemo(
    () => (cfg?.cerebras_simulated ? "Simulated agent" : `Cerebras ${cfg?.cerebras_model}`),
    [cfg]
  );
  const liveActive = phase === "investigating" || phase === "remediating";

  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1.6fr_1fr]">
      {/* Left: live investigation timeline */}
      <section className="glass flex flex-col p-5">
        <div className="mb-4 flex flex-wrap items-center gap-3">
          {scenarios.length > 0 && (
            <select
              value={scenarioId}
              disabled={busy || phase !== "idle"}
              onChange={(e) => setScenarioId(e.target.value)}
              className="rounded-lg border border-edge bg-elevated px-3 py-2 text-xs font-medium text-slate-200 disabled:opacity-50"
            >
              {scenarios.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.title}
                </option>
              ))}
            </select>
          )}
          <button disabled={busy} onClick={() => trigger("alert")} className="btn-danger">
            <Alert className="h-4 w-4" /> Simulate job-failed alert
          </button>
          <button disabled={busy} onClick={() => trigger("manual")} className="btn-ghost">
            <Play className="h-4 w-4" /> Start manually
          </button>

          <div className="ml-auto flex items-center gap-2">
            <div className={`flex items-center gap-2 rounded-lg border px-3 py-1.5 ${meta.cls}`}>
              <span className="relative flex h-2 w-2">
                <span className={`dot h-2 w-2 ${meta.dot} ${liveActive ? "live" : ""}`} />
              </span>
              <span className="text-xs font-semibold">{meta.label}</span>
            </div>
          </div>
        </div>

        <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-xl border border-edge bg-ink/40 px-3.5 py-2.5 text-[12px]">
          <span className="text-muted">
            Engine <span className="font-semibold text-cerebras">{engine}</span>
          </span>
          <span className="h-3 w-px bg-edge" />
          <span className="text-muted">
            Commander + 3 specialists - {actions.length || 0} actions
          </span>
          {elapsedMs != null && (
            <span className="ml-auto flex items-center gap-1.5 font-semibold text-ok">
              <Check className="h-3.5 w-3.5" />
              Investigated in {(elapsedMs / 1000).toFixed(2)}s
            </span>
          )}
        </div>

        <AgentTimeline events={events} />
      </section>

      {/* Right: snapshot, root cause, remediation */}
      <section className="space-y-5">
        <ScreenshotDrop
          disabled={busy || phase !== "idle"}
          onPick={(uri) => (manualSnapshot.current = uri)}
        />
        {rootCause && <RootCauseCard rc={rootCause} />}
        {candidates.length > 0 && <HypothesisRaceCard candidates={candidates} />}
        <RemediationPanel
          actions={actions}
          awaiting={phase === "awaiting"}
          onApprove={doApprove}
          onReject={doReject}
          busy={busy}
        />
        {impact && phase === "resolved" && <ImpactCard impact={impact} />}
        {guardrail && <PreventionCard guardrail={guardrail} />}
        {phase === "resolved" && (
          <div className="glass flex items-start gap-3 border-ok/30 bg-ok/[0.06] p-4">
            <div className="grid h-9 w-9 shrink-0 place-items-center rounded-xl border border-ok/30 bg-ok/10 text-ok">
              <Check className="h-5 w-5" />
            </div>
            <div>
              <div className="text-sm font-semibold text-ok">Incident resolved</div>
              <div className="mt-0.5 text-[12.5px] leading-relaxed text-slate-300">
                CereMind applied the fix and reran the pipeline to green - then filed a guardrail so
                this failure class can't recur. Full audit trail retained.
              </div>
            </div>
          </div>
        )}
        {phase === "failed" && (
          <div className="glass flex items-start gap-3 border-bad/30 bg-bad/[0.06] p-4">
            <div className="grid h-9 w-9 shrink-0 place-items-center rounded-xl border border-bad/30 bg-bad/10 text-bad">
              <Alert className="h-5 w-5" />
            </div>
            <div>
              <div className="text-sm font-semibold text-bad">Rolled back + escalated</div>
              <div className="mt-0.5 text-[12.5px] leading-relaxed text-slate-300">
                The fix didn't verify green, so CereMind reverted its own change and escalated to
                on-call with the full investigation - autonomy with a seatbelt.
              </div>
            </div>
          </div>
        )}
        {phase === "idle" && (
          <div className="glass flex items-start gap-3 p-4 text-[12.5px] text-muted">
            <Shield className="mt-0.5 h-4 w-4 shrink-0 text-accent2" />
            CereMind investigates autonomously and read-only. Any fix that changes state pauses for
            your one-click approval.
          </div>
        )}
      </section>
    </div>
  );
}

function HypothesisRaceCard({ candidates }: { candidates: CandidateFix[] }) {
  return (
    <div className="glass overflow-hidden">
      <div className="flex items-center gap-2 border-b border-edge/70 px-4 py-3 text-[11px] font-bold uppercase tracking-wider text-cerebras">
        <Bolt className="h-4 w-4" /> Hypothesis race
        <span className="ml-auto font-medium normal-case text-muted">
          {candidates.length} fixes scored in parallel
        </span>
      </div>
      <div className="space-y-2 p-4">
        {candidates.map((c, i) => {
          const pct = Math.round(c.predicted_green * 100);
          return (
            <div
              key={i}
              className={`rounded-xl border p-3 ${
                c.chosen ? "border-ok/40 bg-ok/[0.06]" : "border-edge bg-panel2/60"
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-[13px] font-semibold text-slate-100">
                  {c.label}
                  {c.chosen && <span className="ml-2 text-[11px] font-bold text-ok">CHOSEN</span>}
                </span>
                <span className="text-xs font-semibold text-slate-300">{pct}% green</span>
              </div>
              <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-ink">
                <div
                  className={`h-full rounded-full ${c.chosen ? "bg-ok" : "bg-muted"}`}
                  style={{ width: `${pct}%` }}
                />
              </div>
              {c.predicted_outcome && (
                <div className="mt-1.5 text-[12px] leading-relaxed text-muted">
                  {c.predicted_outcome}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ImpactCard({ impact }: { impact: Impact }) {
  return (
    <div className="glass flex items-center gap-4 p-4">
      <div className="flex-1">
        <div className="text-[10px] font-bold uppercase tracking-wider text-muted">MTTR</div>
        <div className="text-lg font-extrabold text-ok">{impact.mttr_min.toFixed(1)} min</div>
        <div className="text-[11px] text-muted">vs ~{impact.human_baseline_min} min human baseline</div>
      </div>
      <div className="h-10 w-px bg-edge" />
      <div className="flex-1">
        <div className="text-[10px] font-bold uppercase tracking-wider text-muted">
          Downtime avoided
        </div>
        <div className="text-lg font-extrabold text-ok">
          ${impact.dollars_avoided.toLocaleString(undefined, { maximumFractionDigits: 0 })}
        </div>
        <div className="text-[11px] text-muted">estimated, this incident</div>
      </div>
    </div>
  );
}

function PreventionCard({ guardrail }: { guardrail: Guardrail }) {
  return (
    <div className="glass overflow-hidden">
      <div className="flex items-center gap-2 border-b border-edge/70 bg-gradient-to-r from-ok/10 to-transparent px-4 py-3 text-[11px] font-bold uppercase tracking-wider text-ok">
        <Shield className="h-4 w-4" /> Immunize - prevention filed
        {guardrail.artifact_id && (
          <span className="ml-auto font-mono text-[11px] font-semibold text-slate-300">
            {guardrail.artifact_id}
          </span>
        )}
      </div>
      <div className="p-4">
        <div className="text-[13.5px] font-semibold text-slate-100">{guardrail.title}</div>
        <div className="mt-1.5 text-[12.5px] leading-relaxed text-slate-300">{guardrail.policy}</div>
        {guardrail.rationale && (
          <div className="mt-2 text-[12px] leading-relaxed text-muted">{guardrail.rationale}</div>
        )}
      </div>
    </div>
  );
}
