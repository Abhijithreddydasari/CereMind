import { useCallback, useMemo, useRef, useState } from "react";
import {
  approve,
  fireAlert,
  reject,
  startManual,
  streamIncident,
  type AgentEvent,
  type AppConfig,
  type ProposedAction,
  type RootCause,
} from "../lib/api";
import AgentTimeline from "./AgentTimeline";
import RootCauseCard from "./RootCauseCard";
import RemediationPanel from "./RemediationPanel";
import ScreenshotDrop from "./ScreenshotDrop";
import { Alert, Check, Play, Shield } from "./icons";

type Phase = "idle" | "investigating" | "awaiting" | "remediating" | "resolved" | "failed";

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
  const [phase, setPhase] = useState<Phase>("idle");
  const [incidentId, setIncidentId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [elapsedMs, setElapsedMs] = useState<number | null>(null);
  const manualSnapshot = useRef<string | undefined>(undefined);
  const closeRef = useRef<null | (() => void)>(null);

  const onEvent = useCallback((e: AgentEvent) => {
    setEvents((prev) => [...prev, e]);
    switch (e.type) {
      case "root_cause":
        setRootCause(e.data as RootCause);
        setActions(((e.data as RootCause).proposed_actions ?? []).map((a) => ({ ...a })));
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
      case "summary":
        setPhase(e.data?.resolved ? "resolved" : "failed");
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
        kind === "alert" ? await fireAlert() : await startManual(manualSnapshot.current);
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
        <RemediationPanel
          actions={actions}
          awaiting={phase === "awaiting"}
          onApprove={doApprove}
          onReject={doReject}
          busy={busy}
        />
        {phase === "resolved" && (
          <div className="glass flex items-start gap-3 border-ok/30 bg-ok/[0.06] p-4">
            <div className="grid h-9 w-9 shrink-0 place-items-center rounded-xl border border-ok/30 bg-ok/10 text-ok">
              <Check className="h-5 w-5" />
            </div>
            <div>
              <div className="text-sm font-semibold text-ok">Incident resolved</div>
              <div className="mt-0.5 text-[12.5px] leading-relaxed text-slate-300">
                CereMind reverted the offending config and reran the nightly ETL to green - with a
                full audit trail.
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
