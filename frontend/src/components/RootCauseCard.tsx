import type { RootCause } from "../lib/api";
import { Target } from "./icons";

const SOURCE_COLOR: Record<string, string> = {
  job_log: "border-cyan/30 bg-cyan/10 text-cyan",
  metrics: "border-ok/30 bg-ok/10 text-ok",
  config_change: "border-warn/30 bg-warn/10 text-warn",
  runbook: "border-accent/30 bg-accent/10 text-accent2",
  incident: "border-pink-400/30 bg-pink-400/10 text-pink-300",
  vision: "border-cerebras/30 bg-cerebras/10 text-cerebras",
};

export default function RootCauseCard({ rc }: { rc: RootCause }) {
  const pct = Math.round(rc.confidence * 100);
  return (
    <div className="glass overflow-hidden">
      <div className="border-b border-edge/70 bg-gradient-to-r from-accent/10 to-transparent px-4 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-wider text-accent2">
            <Target className="h-4 w-4" /> Root cause
          </div>
          <div className="flex items-center gap-2">
            <div className="h-1.5 w-28 overflow-hidden rounded-full bg-ink">
              <div
                className="h-full rounded-full bg-gradient-to-r from-accent to-cerebras"
                style={{ width: `${pct}%` }}
              />
            </div>
            <span className="text-xs font-semibold text-slate-300">{pct}%</span>
          </div>
        </div>
        <div className="mt-2 text-[14.5px] font-medium leading-relaxed text-slate-100">
          {rc.root_cause}
        </div>
      </div>

      <div className="space-y-2.5 p-4">
        {rc.hypotheses.map((h, i) => (
          <div key={i} className="rounded-xl border border-edge bg-panel2/60 p-3">
            <div className="flex items-start justify-between gap-3">
              <div className="text-[13px] font-medium text-slate-200">{h.claim}</div>
              <span className="shrink-0 rounded-md bg-ink px-1.5 py-0.5 text-[11px] font-semibold text-muted">
                {Math.round(h.likelihood * 100)}%
              </span>
            </div>
            {h.evidence.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {h.evidence.map((ev, j) => (
                  <span
                    key={j}
                    title={ev.detail}
                    className={`pill ${SOURCE_COLOR[ev.source] ?? "border-edge bg-ink text-muted"}`}
                  >
                    <span className="font-semibold">{ev.source}</span>
                    <span className="opacity-70">{ev.ref}</span>
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
