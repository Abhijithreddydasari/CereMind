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

type Phase = "idle" | "investigating" | "awaiting" | "remediating" | "resolved" | "failed";

const PHASE_META: Record<Phase, { label: string; cls: string }> = {
  idle: { label: "Idle", cls: "text-slate-400" },
  investigating: { label: "Investigating", cls: "text-sky-400" },
  awaiting: { label: "Awaiting approval", cls: "text-warn" },
  remediating: { label: "Remediating", cls: "text-accent" },
  resolved: { label: "Resolved - pipeline green", cls: "text-ok" },
  failed: { label: "Needs attention", cls: "text-bad" },
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
    () => (cfg?.cerebras_simulated ? "simulated agent" : `Cerebras ${cfg?.cerebras_model}`),
    [cfg]
  );

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1.55fr_1fr]">
      {/* Left: live investigation timeline */}
      <section className="rounded-2xl border border-edge bg-panel/60 p-4">
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <button
            disabled={busy}
            onClick={() => trigger("alert")}
            className="rounded-lg bg-gradient-to-r from-bad to-warn px-4 py-2 text-sm font-bold text-white transition hover:brightness-110 disabled:opacity-50"
          >
            Simulate job-failed alert
          </button>
          <button
            disabled={busy}
            onClick={() => trigger("manual")}
            className="rounded-lg border border-edge px-3 py-2 text-sm font-medium text-slate-300 transition hover:bg-panel2 disabled:opacity-50"
          >
            Start manually
          </button>
          <div className="ml-auto flex items-center gap-2">
            <span className={`text-sm font-semibold ${meta.cls}`}>{meta.label}</span>
            {(phase === "investigating" || phase === "remediating") && (
              <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-current opacity-70" />
            )}
          </div>
        </div>

        <div className="mb-3 flex items-center gap-3 rounded-lg border border-edge bg-panel2 px-3 py-2 text-[12px] text-slate-400">
          <span>
            Engine: <span className="text-cerebras">{engine}</span>
          </span>
          {elapsedMs != null && (
            <span className="ml-auto">
              Investigation completed in{" "}
              <span className="font-bold text-ok">{(elapsedMs / 1000).toFixed(2)}s</span>
            </span>
          )}
        </div>

        <AgentTimeline events={events} />
      </section>

      {/* Right: snapshot, root cause, remediation */}
      <section className="space-y-4">
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
          <div className="rounded-xl border border-ok/40 bg-ok/10 p-3 text-sm text-ok">
            Incident resolved. CereMind reverted the offending config and reran the nightly
            ETL to green - with a full audit trail.
          </div>
        )}
      </section>
    </div>
  );
}
