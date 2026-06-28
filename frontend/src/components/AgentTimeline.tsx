import { useEffect, useRef } from "react";
import type { AgentEvent } from "../lib/api";

const ACTOR_COLOR: Record<string, string> = {
  commander: "text-accent",
  telemetry: "text-sky-400",
  change: "text-amber-400",
  knowledge: "text-emerald-400",
  system: "text-slate-400",
};

const TYPE_LABEL: Record<string, string> = {
  incident_opened: "ALERT",
  vision: "VISION",
  thought: "THINK",
  specialist_start: "AGENT",
  specialist_done: "FINDING",
  tool_call: "TOOL",
  observation: "OBS",
  root_cause: "ROOT CAUSE",
  action_proposed: "PROPOSE",
  awaiting_approval: "GATE",
  action_executed: "EXEC",
  verification: "VERIFY",
  summary: "SUMMARY",
  error: "ERROR",
  done: "DONE",
};

function dot(type: string) {
  if (type === "error") return "bg-bad";
  if (type === "verification" || type === "summary" || type === "done") return "bg-ok";
  if (type === "awaiting_approval") return "bg-warn";
  if (type === "tool_call") return "bg-sky-400";
  if (type === "root_cause") return "bg-accent";
  return "bg-slate-500";
}

function Row({ e }: { e: AgentEvent }) {
  const color = ACTOR_COLOR[e.actor] ?? "text-slate-300";
  const isObs = e.type === "observation" || e.type === "tool_call";
  return (
    <div className="fadein flex gap-3">
      <div className="flex flex-col items-center">
        <div className={`mt-1.5 h-2.5 w-2.5 rounded-full ${dot(e.type)}`} />
        <div className="w-px flex-1 bg-edge" />
      </div>
      <div className="pb-3">
        <div className="flex items-center gap-2">
          <span className="rounded bg-panel2 px-1.5 py-0.5 text-[10px] font-bold tracking-wide text-slate-400">
            {TYPE_LABEL[e.type] ?? e.type}
          </span>
          <span className={`text-[11px] font-semibold uppercase ${color}`}>{e.actor}</span>
          {e.title && <span className="text-sm font-medium text-slate-200">{e.title}</span>}
        </div>
        {e.detail && (
          <div
            className={`mt-1 whitespace-pre-wrap text-[13px] leading-relaxed ${
              isObs ? "font-mono text-slate-400" : "text-slate-300"
            }`}
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
      <div className="grid h-full min-h-[300px] place-items-center text-sm text-slate-500">
        Trigger an alert to watch CereMind investigate live.
      </div>
    );
  }

  return (
    <div className="max-h-[62vh] overflow-y-auto pr-2">
      {events.map((e) => (
        <Row key={e.id} e={e} />
      ))}
      <div ref={endRef} />
    </div>
  );
}
