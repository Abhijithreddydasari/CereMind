import { useEffect, useRef } from "react";
import type { AgentEvent } from "../lib/api";
import {
  Activity,
  Alert,
  Bolt,
  Brain,
  Check,
  Doc,
  Eye,
  Gear,
  Search,
  Shield,
  Sparkle,
  Target,
  Wrench,
  X,
} from "./icons";

const ACTOR_COLOR: Record<string, string> = {
  commander: "text-accent2",
  telemetry: "text-cyan",
  change: "text-warn",
  knowledge: "text-ok",
  system: "text-muted",
};

const TYPE_META: Record<
  string,
  { label: string; icon: (p: any) => JSX.Element; color: string }
> = {
  incident_opened: { label: "Alert", icon: Alert, color: "text-bad" },
  vision: { label: "Vision", icon: Eye, color: "text-cerebras" },
  thought: { label: "Reasoning", icon: Brain, color: "text-accent2" },
  specialist_start: { label: "Agent", icon: Sparkle, color: "text-slate-200" },
  specialist_done: { label: "Finding", icon: Check, color: "text-ok" },
  tool_call: { label: "Tool", icon: Gear, color: "text-cyan" },
  observation: { label: "Observation", icon: Search, color: "text-muted" },
  root_cause: { label: "Root cause", icon: Target, color: "text-accent2" },
  hypothesis_race: { label: "Race", icon: Bolt, color: "text-cerebras" },
  action_proposed: { label: "Proposed", icon: Wrench, color: "text-warn" },
  awaiting_approval: { label: "Gate", icon: Shield, color: "text-warn" },
  action_executed: { label: "Executed", icon: Wrench, color: "text-ok" },
  verification: { label: "Verify", icon: Check, color: "text-ok" },
  rollback: { label: "Rollback", icon: Alert, color: "text-bad" },
  immunize: { label: "Immunize", icon: Shield, color: "text-ok" },
  summary: { label: "Summary", icon: Doc, color: "text-ok" },
  error: { label: "Error", icon: X, color: "text-bad" },
  done: { label: "Done", icon: Check, color: "text-ok" },
};

const SPECIALIST_ICON: Record<string, (p: any) => JSX.Element> = {
  telemetry: Activity,
  change: Gear,
  knowledge: Doc,
  commander: Brain,
};

function Row({ e, last }: { e: AgentEvent; last: boolean }) {
  const meta = TYPE_META[e.type] ?? { label: e.type, icon: Activity, color: "text-muted" };
  const Icon = SPECIALIST_ICON[e.actor] && e.type === "specialist_start"
    ? SPECIALIST_ICON[e.actor]
    : meta.icon;
  const actorColor = ACTOR_COLOR[e.actor] ?? "text-slate-300";
  const isMono = e.type === "observation" || e.type === "tool_call";

  return (
    <div className="group relative flex gap-3.5 animate-fadein">
      {/* node + connector */}
      <div className="flex flex-col items-center">
        <div
          className={`grid h-7 w-7 shrink-0 place-items-center rounded-lg border border-edge bg-elevated ${meta.color}`}
        >
          <Icon className="h-3.5 w-3.5" />
        </div>
        {!last && <div className="mt-1 w-px flex-1 bg-gradient-to-b from-edge to-transparent" />}
      </div>

      {/* body */}
      <div className="min-w-0 flex-1 pb-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className={`text-[10px] font-bold uppercase tracking-wider ${meta.color}`}>
            {meta.label}
          </span>
          <span className={`text-[10px] font-semibold uppercase tracking-wide ${actorColor}`}>
            {e.actor}
          </span>
          {e.title && (
            <span className="text-[13.5px] font-semibold text-slate-100">{e.title}</span>
          )}
        </div>
        {e.detail && (
          <div
            className={
              isMono
                ? "mt-1.5 overflow-x-auto rounded-lg border border-edge/70 bg-ink/60 px-3 py-2 font-mono text-[11.5px] leading-relaxed text-slate-400"
                : "mt-1 whitespace-pre-wrap text-[13px] leading-relaxed text-slate-300"
            }
          >
            {e.detail}
          </div>
        )}
      </div>
    </div>
  );
}

export default function AgentTimeline({ events }: { events: AgentEvent[] }) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [events.length]);

  if (events.length === 0) {
    return (
      <div className="grid min-h-[340px] place-items-center">
        <div className="text-center">
          <div className="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-2xl border border-edge bg-elevated/60">
            <Activity className="h-6 w-6 text-muted" />
          </div>
          <div className="text-sm font-medium text-slate-300">No active incident</div>
          <div className="mt-1 text-[13px] text-muted">
            Fire an alert to watch CereMind investigate in real time.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="max-h-[64vh] overflow-y-auto pr-1.5">
      {events.map((e, i) => (
        <Row key={e.id} e={e} last={i === events.length - 1} />
      ))}
      <div ref={endRef} />
    </div>
  );
}
