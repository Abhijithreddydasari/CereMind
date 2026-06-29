import { useEffect, useRef, useState } from "react";
import { streamSpeed, type AgentEvent, type AppConfig, type SpeedEvent } from "../lib/api";
import AgentTimeline from "./AgentTimeline";
import { Bolt, Play } from "./icons";

interface PaneState {
  events: AgentEvent[];
  eventCount: number;
  tokens: number;
  tps: number;
  ttftMs: number;
  elapsedMs: number;
  done: boolean;
  error?: string | null;
}
const EMPTY: PaneState = {
  events: [],
  eventCount: 0,
  tokens: 0,
  tps: 0,
  ttftMs: 0,
  elapsedMs: 0,
  done: false,
};

function money(value: number): string {
  return value.toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: value >= 100 ? 0 : 2,
  });
}

function seconds(ms: number): string {
  return `${(ms / 1000).toFixed(2)}s`;
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div className="rounded-xl border border-edge bg-ink/50 px-3 py-2 text-center">
      <div className={`text-lg font-extrabold tabular-nums ${accent ?? "text-slate-100"}`}>
        {value}
      </div>
      <div className="text-[10px] font-medium uppercase tracking-wider text-muted">{label}</div>
    </div>
  );
}

function Pane({
  title,
  subtitle,
  accent,
  ring,
  state,
  winner,
}: {
  title: string;
  subtitle: string;
  accent: string;
  ring: string;
  state: PaneState;
  winner: boolean;
}) {
  return (
    <div
      className={`glass relative flex flex-col p-5 transition ${
        winner ? ring : ""
      }`}
    >
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2.5">
          <div className={`grid h-9 w-9 place-items-center rounded-xl border border-edge bg-elevated ${accent}`}>
            <Bolt className="h-4 w-4" />
          </div>
          <div>
            <div className={`text-[15px] font-bold ${accent}`}>{title}</div>
            <div className="text-[11px] text-muted">{subtitle}</div>
          </div>
        </div>
        {winner && state.done && (
          <span className="pill border-ok/40 bg-ok/15 text-ok">fastest</span>
        )}
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="tokens/sec" value={state.tps ? state.tps.toFixed(1) : "-"} accent={accent} />
        <Stat label="time to 1st token" value={state.ttftMs ? `${(state.ttftMs / 1000).toFixed(2)}s` : "-"} />
        <Stat label="elapsed" value={`${(state.elapsedMs / 1000).toFixed(2)}s`} />
        <Stat label="tokens" value={state.tokens ? state.tokens.toLocaleString() : "-"} />
      </div>

      <div className="relative mt-4 min-h-[240px] flex-1 overflow-hidden rounded-xl border border-edge bg-ink/45 p-3.5">
        {state.error ? (
          <div className="rounded-lg border border-bad/30 bg-bad/[0.06] px-3 py-2 text-[12.5px] leading-relaxed text-bad">
            {state.error}
          </div>
        ) : (
          <AgentTimeline
            events={state.events}
            emptyTitle="Waiting for race"
            emptyDescription="Run the comparison to watch this engine investigate the incident."
          />
        )}
      </div>
      <div className="mt-2 text-right text-[10.5px] text-muted">
        {state.eventCount ? `${state.eventCount} incident events rendered` : "Provider tokens counted from LLM usage"}
      </div>
    </div>
  );
}

function ResultSummary({
  speedup,
  tokenSpeedup,
  savedMs,
  dollarsSaved,
  costPerMin,
  cerebras,
  baseline,
}: {
  speedup: number | null;
  tokenSpeedup: number | null;
  savedMs: number;
  dollarsSaved: number | null;
  costPerMin: number | null;
  cerebras: PaneState;
  baseline: PaneState;
}) {
  return (
    <div className="glass mb-5 overflow-hidden border-ok/20 bg-ok/[0.04]">
      <div className="flex flex-wrap items-center gap-2 border-b border-edge/70 px-4 py-3">
        <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-wider text-ok">
          <Bolt className="h-4 w-4" /> Final race result
        </div>
        <div className="ml-auto text-[11px] text-muted">
          Based on this completed side-by-side incident run
        </div>
      </div>
      <div className="grid gap-3 p-4 md:grid-cols-3">
        <div className="rounded-xl border border-edge bg-ink/45 p-3">
          <div className="text-[10px] font-bold uppercase tracking-wider text-muted">
            Incident wall-clock
          </div>
          <div className="mt-1 text-2xl font-extrabold text-ok">
            {speedup ? `${speedup.toFixed(1)}x faster` : "-"}
          </div>
          <div className="mt-1 text-[11px] leading-relaxed text-muted">
            Cerebras {seconds(cerebras.elapsedMs)} vs GPU {seconds(baseline.elapsedMs)}
          </div>
        </div>
        <div className="rounded-xl border border-edge bg-ink/45 p-3">
          <div className="text-[10px] font-bold uppercase tracking-wider text-muted">
            Token generation
          </div>
          <div className="mt-1 text-2xl font-extrabold text-cerebras">
            {tokenSpeedup ? `${tokenSpeedup.toFixed(1)}x faster` : "-"}
          </div>
          <div className="mt-1 text-[11px] leading-relaxed text-muted">
            {cerebras.tps.toFixed(1)} tok/s vs {baseline.tps.toFixed(1)} tok/s
          </div>
        </div>
        <div className="rounded-xl border border-edge bg-ink/45 p-3">
          <div className="text-[10px] font-bold uppercase tracking-wider text-muted">
            Cost impact
          </div>
          <div className="mt-1 text-2xl font-extrabold text-ok">
            {dollarsSaved != null ? money(dollarsSaved) : "-"}
          </div>
          <div className="mt-1 text-[11px] leading-relaxed text-muted">
            {savedMs > 0 ? `${seconds(savedMs)} saved` : "No time saved"}
            {costPerMin != null ? ` at ${money(costPerMin)}/min` : ""}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function SpeedCompare({ cfg }: { cfg: AppConfig | null }) {
  const [cerebras, setCerebras] = useState<PaneState>(EMPTY);
  const [baseline, setBaseline] = useState<PaneState>(EMPTY);
  const [running, setRunning] = useState(false);
  const [costPerMin, setCostPerMin] = useState<number | null>(null);
  const closeRef = useRef<null | (() => void)>(null);

  function run() {
    setCerebras(EMPTY);
    setBaseline(EMPTY);
    setCostPerMin(null);
    setRunning(true);
    closeRef.current?.();
    closeRef.current = streamSpeed((e: SpeedEvent) => {
      if (e.type === "start") {
        setCostPerMin(typeof e.cost_per_min === "number" ? e.cost_per_min : null);
      } else if (e.type === "token" && e.engine) {
        const upd = (p: PaneState): PaneState => ({
          ...p,
          tokens: e.tokens ?? p.tokens,
          tps: e.tps ?? p.tps,
          ttftMs: e.ttft_ms ?? p.ttftMs,
          elapsedMs: e.elapsed_ms ?? p.elapsedMs,
        });
        e.engine === "cerebras" ? setCerebras(upd) : setBaseline(upd);
      } else if (e.type === "agent_event" && e.engine && e.event) {
        const append = (p: PaneState): PaneState => ({
          ...p,
          events: [...p.events, e.event as AgentEvent],
          eventCount: e.events ?? p.eventCount + 1,
          tokens: e.tokens ?? p.tokens,
          tps: e.tps ?? p.tps,
          ttftMs: e.ttft_ms ?? p.ttftMs,
          elapsedMs: e.elapsed_ms ?? p.elapsedMs,
        });
        e.engine === "cerebras" ? setCerebras(append) : setBaseline(append);
      } else if (e.type === "engine_done" && e.engine) {
        const fin = (p: PaneState): PaneState => ({
          ...p,
          done: true,
          tps: e.tps ?? p.tps,
          ttftMs: e.ttft_ms ?? p.ttftMs,
          elapsedMs: e.elapsed_ms ?? p.elapsedMs,
          tokens: e.tokens ?? p.tokens,
          eventCount: e.events ?? p.eventCount,
          error: e.error ?? null,
        });
        e.engine === "cerebras" ? setCerebras(fin) : setBaseline(fin);
      } else if (e.type === "done") {
        setRunning(false);
      }
    }, () => setRunning(false));
  }

  useEffect(() => {
    if (running && cerebras.done && baseline.done) setRunning(false);
  }, [baseline.done, cerebras.done, running]);

  // Headline speedup for the full incident investigation wall-clock.
  const complete =
    cerebras.done && baseline.done && !cerebras.error && !baseline.error;
  const speedup =
    complete &&
    cerebras.elapsedMs > 0 &&
    baseline.elapsedMs > 0
      ? baseline.elapsedMs / cerebras.elapsedMs
      : null;
  const cerebrasWon = !!speedup && speedup > 1;
  const tokenSpeedup =
    complete && cerebras.tps > 0 && baseline.tps > 0 ? cerebras.tps / baseline.tps : null;
  const savedMs =
    cerebrasWon && baseline.elapsedMs > cerebras.elapsedMs
      ? baseline.elapsedMs - cerebras.elapsedMs
      : 0;
  const dollarsSaved =
    costPerMin != null && savedMs > 0 ? (savedMs / 60000) * costPerMin : null;

  return (
    <div>
      <div className="glass mb-5 flex flex-wrap items-center gap-3 p-4">
        <button disabled={running} onClick={run} className="btn-primary">
          {running ? (
            <>
              <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white" />
              Investigating...
            </>
          ) : (
            <>
              <Play className="h-4 w-4" /> Run the same incident on both
            </>
          )}
        </button>
        {cerebrasWon && (
          <div className="pill border-ok/40 bg-ok/15 px-3 py-2 text-sm font-bold text-ok">
            <Bolt className="h-4 w-4" /> Cerebras ~{speedup.toFixed(1)}x faster
          </div>
        )}
        {dollarsSaved != null && dollarsSaved > 0 && (
          <div className="pill border-cerebras/40 bg-cerebras/10 px-3 py-2 text-sm font-bold text-cerebras">
            {money(dollarsSaved)} approx saved
          </div>
        )}
        <div className="ml-auto max-w-sm text-right text-[11px] leading-relaxed text-muted">
          Same incident system flow, measured with generated completion tokens.{" "}
          {cfg?.baseline_simulated
            ? "GPU pane uses a representative Modal pace (set BASELINE_* to race a real endpoint)."
            : "GPU pane runs the incident commander on a Modal endpoint - a true side-by-side."}
        </div>
      </div>

      {complete && (
        <ResultSummary
          speedup={speedup}
          tokenSpeedup={tokenSpeedup}
          savedMs={savedMs}
          dollarsSaved={dollarsSaved}
          costPerMin={costPerMin}
          cerebras={cerebras}
          baseline={baseline}
        />
      )}

      <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
        <Pane
          title={cfg?.cerebras_simulated ? "Gemma 4 - Cerebras (sim)" : "Gemma 4 - Cerebras"}
          subtitle="Wafer-scale inference"
          accent="text-cerebras"
          ring="shadow-[0_0_0_1px_rgba(52,211,153,0.5),0_24px_60px_-24px_rgba(52,211,153,0.5)]"
          state={cerebras}
          winner={cerebrasWon}
        />
        <Pane
          title={cfg?.baseline_label ?? "Gemma 4 - GPU baseline"}
          subtitle="Single GPU - vLLM on Modal"
          accent="text-slate-300"
          ring=""
          state={baseline}
          winner={false}
        />
      </div>
    </div>
  );
}
