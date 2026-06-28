// API client + shared types for the CereMind war-room console.

export type EventType =
  | "incident_opened"
  | "vision"
  | "thought"
  | "specialist_start"
  | "specialist_done"
  | "tool_call"
  | "observation"
  | "root_cause"
  | "action_proposed"
  | "awaiting_approval"
  | "action_executed"
  | "verification"
  | "summary"
  | "error"
  | "done";

export interface AgentEvent {
  id: string;
  incident_id: string;
  ts: number;
  type: EventType;
  actor: string;
  title: string;
  detail: string;
  data: Record<string, any>;
}

export interface Evidence {
  source: string;
  ref: string;
  detail: string;
}
export interface Hypothesis {
  claim: string;
  likelihood: number;
  evidence: Evidence[];
}
export interface ProposedAction {
  id: string;
  action: string;
  args: Record<string, any>;
  risk_tier: number;
  rationale: string;
  status: string;
  result?: string;
}
export interface RootCause {
  root_cause: string;
  confidence: number;
  hypotheses: Hypothesis[];
  proposed_actions: ProposedAction[];
}

export interface AppConfig {
  cerebras_model: string;
  cerebras_simulated: boolean;
  baseline_label: string;
  baseline_simulated: boolean;
  embedding_backend: string;
  vector_backend: string;
  pipeline_backend: string;
}

const json = { "Content-Type": "application/json" };

export async function getConfig(): Promise<AppConfig> {
  const r = await fetch("/api/config");
  return r.json();
}

export async function fireAlert(): Promise<{ incident_id: string }> {
  const r = await fetch("/api/incidents/webhook", {
    method: "POST",
    headers: json,
    body: "{}",
  });
  return r.json();
}

export async function startManual(snapshotDataUri?: string): Promise<{ incident_id: string }> {
  const body = {
    source: "manual",
    title: "acmeshop_nightly_etl failed at transform",
    job_id: "acmeshop_nightly_etl",
    failed_task: "transform",
    summary: "Engineer-initiated investigation.",
    snapshot_data_uri: snapshotDataUri ?? null,
    attach_seeded_snapshot: !snapshotDataUri,
  };
  const r = await fetch("/api/incidents/start", {
    method: "POST",
    headers: json,
    body: JSON.stringify(body),
  });
  return r.json();
}

export async function approve(incidentId: string) {
  return fetch(`/api/incidents/${incidentId}/approve`, { method: "POST" });
}
export async function reject(incidentId: string) {
  return fetch(`/api/incidents/${incidentId}/reject`, { method: "POST" });
}

export function streamIncident(
  incidentId: string,
  onEvent: (e: AgentEvent) => void,
  onClose?: () => void
): () => void {
  const es = new EventSource(`/api/incidents/${incidentId}/stream`);
  es.onmessage = (m) => {
    try {
      const e = JSON.parse(m.data) as AgentEvent;
      onEvent(e);
      if (e.type === "done") {
        es.close();
        onClose?.();
      }
    } catch {
      /* keep-alive */
    }
  };
  es.onerror = () => {
    es.close();
    onClose?.();
  };
  return () => es.close();
}

export interface SpeedEvent {
  type: "start" | "token" | "engine_done" | "done";
  engine?: "cerebras" | "baseline";
  chunk?: string;
  tokens?: number;
  elapsed_ms?: number;
  tps?: number;
  cerebras_model?: string;
  baseline_label?: string;
  cerebras_simulated?: boolean;
  baseline_simulated?: boolean;
}

export function streamSpeed(onEvent: (e: SpeedEvent) => void): () => void {
  const es = new EventSource(`/api/speed/stream`);
  es.onmessage = (m) => {
    try {
      const e = JSON.parse(m.data) as SpeedEvent;
      onEvent(e);
      if (e.type === "done") es.close();
    } catch {
      /* noop */
    }
  };
  es.onerror = () => es.close();
  return () => es.close();
}

export const snapshotUrl = "/api/incidents/snapshot.png";
