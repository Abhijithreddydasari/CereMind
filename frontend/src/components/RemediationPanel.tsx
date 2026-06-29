import type { ProposedAction } from "../lib/api";
import { Check, Shield, Wrench, X } from "./icons";

const TIER: Record<number, { label: string; cls: string }> = {
  0: { label: "Tier 0 - read only", cls: "border-ok/30 bg-ok/10 text-ok" },
  1: { label: "Tier 1 - low risk", cls: "border-warn/30 bg-warn/10 text-warn" },
  2: { label: "Tier 2 - approval required", cls: "border-bad/30 bg-bad/10 text-bad" },
};

function fmtArgs(args: Record<string, any>) {
  return Object.entries(args)
    .map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : v}`)
    .join(", ");
}

export default function RemediationPanel({
  actions,
  awaiting,
  onApprove,
  onReject,
  busy,
}: {
  actions: ProposedAction[];
  awaiting: boolean;
  onApprove: () => void;
  onReject: () => void;
  busy: boolean;
}) {
  if (actions.length === 0) return null;
  return (
    <div className="glass overflow-hidden">
      <div className="flex items-center gap-2 border-b border-edge/70 px-4 py-3 text-[11px] font-bold uppercase tracking-wider text-slate-300">
        <Wrench className="h-4 w-4 text-warn" /> Proposed remediation
      </div>

      <div className="space-y-2 p-4">
        {actions.map((a) => {
          const tier = TIER[a.risk_tier] ?? TIER[2];
          return (
            <div key={a.id} className="rounded-xl border border-edge bg-panel2/60 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <code className="font-mono text-[13px] font-semibold text-slate-100">
                  {a.action}
                  <span className="text-muted">({fmtArgs(a.args)})</span>
                </code>
                <span className={`pill ${tier.cls}`}>{tier.label}</span>
              </div>
              <div className="mt-1.5 text-[12.5px] leading-relaxed text-muted">{a.rationale}</div>
              {a.status === "executed" && (
                <div className="mt-2 flex items-center gap-1.5 rounded-lg border border-ok/25 bg-ok/10 px-2.5 py-1.5 text-[12px] text-ok">
                  <Check className="h-3.5 w-3.5" /> {a.result}
                </div>
              )}
              {a.status === "failed" && (
                <div className="mt-2 flex items-center gap-1.5 rounded-lg border border-bad/25 bg-bad/10 px-2.5 py-1.5 text-[12px] text-bad">
                  <X className="h-3.5 w-3.5" /> {a.result}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {awaiting && (
        <div className="border-t border-edge/70 bg-warn/[0.04] p-3">
          <div className="mb-2 flex items-center gap-1.5 text-[12px] text-warn">
            <Shield className="h-3.5 w-3.5" /> High-risk fix - human approval required
          </div>
          <div className="flex items-center gap-2">
            <button disabled={busy} onClick={onApprove} className="btn-primary flex-1">
              <Check className="h-4 w-4" /> Approve &amp; apply fix
            </button>
            <button disabled={busy} onClick={onReject} className="btn-ghost">
              <X className="h-4 w-4" /> Reject
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
