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
  | "hypothesis_race"
  | "action_proposed"
  | "awaiting_approval"
  | "action_executed"
  | "verification"
  | "rollback"
  | "immunize"
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

export interface CandidateFix {
  action: string;
  args: Record<string, any>;
  label: string;
  predicted_green: number;
  risk_tier: number;
  confidence: number;
  predicted_outcome: string;
  chosen: boolean;
}

export interface Guardrail {
  title: string;
  policy: string;
  rationale: string;
  artifact_kind: string;
  artifact_id?: string;
  artifact_url?: string;
}

export interface Scenario {
  id: string;
  title: string;
  summary: string;
  job_id: string;
  failed_task: string;
  cost_per_min: number;
}

export interface AppConfig {
  cerebras_model: string;
  cerebras_simulated: boolean;
  baseline_label: string;
  baseline_simulated: boolean;
  embedding_backend: string;
  vector_backend: string;
  pipeline_backend: string;
  scenarios?: Scenario[];
}

const json = { "Content-Type": "application/json" };

export async function getConfig(): Promise<AppConfig> {
  const r = await fetch("/api/config");
  return r.json();
}

export async function getScenarios(): Promise<Scenario[]> {
  const r = await fetch("/api/incidents/scenarios");
  const data = await r.json();
  return data.scenarios ?? [];
}

export async function fireAlert(scenarioId?: string): Promise<{ incident_id: string }> {
  const r = await fetch("/api/incidents/webhook", {
    method: "POST",
    headers: json,
    body: JSON.stringify({ scenario_id: scenarioId ?? null }),
  });
  return r.json();
}

export async function startManual(
  snapshotDataUri?: string,
  scenarioId?: string
): Promise<{ incident_id: string }> {
  const body = {
    source: "manual",
    scenario_id: scenarioId ?? null,
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

export const scenarioSnapshotUrl = (scenarioId: string) =>
  `/api/incidents/snapshot.png?scenario_id=${encodeURIComponent(scenarioId)}`;

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
  type: "start" | "token" | "agent_event" | "engine_done" | "done";
  engine?: "cerebras" | "baseline";
  chunk?: string;
  event?: AgentEvent;
  tokens?: number;
  token_delta?: number;
  events?: number;
  elapsed_ms?: number;
  ttft_ms?: number;
  tps?: number;
  error?: string | null;
  cerebras_model?: string;
  baseline_label?: string;
  cerebras_simulated?: boolean;
  baseline_simulated?: boolean;
  cost_per_min?: number;
}

export function streamSpeed(onEvent: (e: SpeedEvent) => void, onClose?: () => void): () => void {
  const es = new EventSource(`/api/speed/stream`);
  es.onmessage = (m) => {
    try {
      const e = JSON.parse(m.data) as SpeedEvent;
      onEvent(e);
      if (e.type === "done") {
        es.close();
        onClose?.();
      }
    } catch {
      /* noop */
    }
  };
  es.onerror = () => {
    es.close();
    onClose?.();
  };
  return () => es.close();
}

export const snapshotUrl = "/api/incidents/snapshot.png";
