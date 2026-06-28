import type { RootCause } from "../lib/api";

const SOURCE_COLOR: Record<string, string> = {
  job_log: "text-sky-400",
  metrics: "text-emerald-400",
  config_change: "text-amber-400",
  runbook: "text-accent",
  incident: "text-pink-400",
  vision: "text-cerebras",
};

export default function RootCauseCard({ rc }: { rc: RootCause }) {
  const pct = Math.round(rc.confidence * 100);
  return (
    <div className="rounded-xl border border-accent/40 bg-panel p-4">
      <div className="mb-2 flex items-center justify-between">
        <div className="text-xs font-semibold uppercase tracking-wide text-accent">
          Root cause
        </div>
        <div className="flex items-center gap-2">
          <div className="h-1.5 w-24 overflow-hidden rounded-full bg-panel2">
            <div className="h-full bg-accent" style={{ width: `${pct}%` }} />
          </div>
          <span className="text-xs text-slate-400">{pct}% conf.</span>
        </div>
      </div>
      <div className="text-[15px] font-medium leading-relaxed text-slate-100">
        {rc.root_cause}
      </div>

      <div className="mt-3 space-y-2">
        {rc.hypotheses.map((h, i) => (
          <div key={i} className="rounded-lg border border-edge bg-panel2 p-2.5">
            <div className="flex items-center justify-between">
              <div className="text-sm text-slate-200">{h.claim}</div>
              <span className="ml-2 shrink-0 text-[11px] text-slate-500">
                {Math.round(h.likelihood * 100)}%
              </span>
            </div>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {h.evidence.map((ev, j) => (
                <span
                  key={j}
                  title={ev.detail}
                  className="rounded border border-edge bg-panel px-1.5 py-0.5 text-[11px]"
                >
                  <span className={SOURCE_COLOR[ev.source] ?? "text-slate-400"}>
                    {ev.source}
                  </span>
                  <span className="text-slate-500">:{ev.ref}</span>
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
