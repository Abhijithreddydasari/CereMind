import type { ProposedAction } from "../lib/api";

const TIER_LABEL: Record<number, { label: string; cls: string }> = {
  0: { label: "Tier 0 - read only", cls: "text-ok border-ok/40" },
  1: { label: "Tier 1 - low risk", cls: "text-warn border-warn/40" },
  2: { label: "Tier 2 - approval required", cls: "text-bad border-bad/40" },
};

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
    <div className="rounded-xl border border-edge bg-panel p-4">
      <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
        Proposed remediation
      </div>
      <div className="space-y-2">
        {actions.map((a) => {
          const tier = TIER_LABEL[a.risk_tier] ?? TIER_LABEL[2];
          return (
            <div key={a.id} className="rounded-lg border border-edge bg-panel2 p-2.5">
              <div className="flex items-center justify-between">
                <code className="text-sm font-semibold text-slate-100">
                  {a.action}({Object.values(a.args).join(", ")})
                </code>
                <span className={`rounded border px-1.5 py-0.5 text-[10px] ${tier.cls}`}>
                  {tier.label}
                </span>
              </div>
              <div className="mt-1 text-[13px] text-slate-400">{a.rationale}</div>
              {a.status === "executed" && (
                <div className="mt-1 text-[12px] text-ok">{a.result}</div>
              )}
              {a.status === "failed" && (
                <div className="mt-1 text-[12px] text-bad">{a.result}</div>
              )}
            </div>
          );
        })}
      </div>

      {awaiting && (
        <div className="mt-3 flex items-center gap-2">
          <button
            disabled={busy}
            onClick={onApprove}
            className="pulse flex-1 rounded-lg bg-ok px-4 py-2 text-sm font-bold text-white transition hover:brightness-110 disabled:opacity-50"
          >
            Approve &amp; apply fix
          </button>
          <button
            disabled={busy}
            onClick={onReject}
            className="rounded-lg border border-edge px-4 py-2 text-sm font-medium text-slate-300 transition hover:bg-panel2 disabled:opacity-50"
          >
            Reject
          </button>
        </div>
      )}
    </div>
  );
}
