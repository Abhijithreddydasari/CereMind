import { useRef, useState } from "react";
import { streamSpeed, type AppConfig, type SpeedEvent } from "../lib/api";

interface PaneState {
  text: string;
  tokens: number;
  tps: number;
  elapsedMs: number;
  done: boolean;
}
const EMPTY: PaneState = { text: "", tokens: 0, tps: 0, elapsedMs: 0, done: false };

function Pane({
  title,
  subtitle,
  accent,
  state,
  winner,
}: {
  title: string;
  subtitle: string;
  accent: string;
  state: PaneState;
  winner: boolean;
}) {
  return (
    <div
      className={`flex flex-col rounded-2xl border bg-panel p-4 transition ${
        winner ? "border-ok shadow-[0_0_30px_-10px] shadow-ok" : "border-edge"
      }`}
    >
      <div className="flex items-center justify-between">
        <div>
          <div className={`text-base font-bold ${accent}`}>{title}</div>
          <div className="text-[11px] text-slate-500">{subtitle}</div>
        </div>
        {winner && state.done && (
          <span className="rounded-full bg-ok/20 px-2 py-0.5 text-[11px] font-bold text-ok">
            fastest
          </span>
        )}
      </div>

      <div className="mt-3 grid grid-cols-3 gap-2">
        <Stat label="tokens/s" value={state.tps ? state.tps.toFixed(0) : "-"} big accent={accent} />
        <Stat label="elapsed" value={`${(state.elapsedMs / 1000).toFixed(2)}s`} />
        <Stat label="tokens" value={`${state.tokens}`} />
      </div>

      <div className="mt-3 min-h-[150px] flex-1 rounded-lg border border-edge bg-ink p-3 font-mono text-[13px] leading-relaxed text-slate-300">
        {state.text || <span className="text-slate-600">waiting...</span>}
        {!state.done && state.text && <span className="ml-0.5 animate-pulse">|</span>}
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  big,
  accent,
}: {
  label: string;
  value: string;
  big?: boolean;
  accent?: string;
}) {
  return (
    <div className="rounded-lg border border-edge bg-panel2 px-2 py-1.5 text-center">
      <div className={`${big ? "text-xl" : "text-sm"} font-bold ${accent ?? "text-slate-200"}`}>
        {value}
      </div>
      <div className="text-[10px] uppercase tracking-wide text-slate-500">{label}</div>
    </div>
  );
}

export default function SpeedCompare({ cfg }: { cfg: AppConfig | null }) {
  const [cerebras, setCerebras] = useState<PaneState>(EMPTY);
  const [baseline, setBaseline] = useState<PaneState>(EMPTY);
  const [running, setRunning] = useState(false);
  const closeRef = useRef<null | (() => void)>(null);

  function run() {
    setCerebras(EMPTY);
    setBaseline(EMPTY);
    setRunning(true);
    closeRef.current?.();
    closeRef.current = streamSpeed((e: SpeedEvent) => {
      if (e.type === "token" && e.engine) {
        const upd = (p: PaneState): PaneState => ({
          ...p,
          text: p.text + (e.chunk ?? ""),
          tokens: e.tokens ?? p.tokens,
          tps: e.tps ?? p.tps,
          elapsedMs: e.elapsed_ms ?? p.elapsedMs,
        });
        e.engine === "cerebras" ? setCerebras(upd) : setBaseline(upd);
      } else if (e.type === "engine_done" && e.engine) {
        const fin = (p: PaneState): PaneState => ({
          ...p,
          done: true,
          tps: e.tps ?? p.tps,
          elapsedMs: e.elapsed_ms ?? p.elapsedMs,
          tokens: e.tokens ?? p.tokens,
        });
        e.engine === "cerebras" ? setCerebras(fin) : setBaseline(fin);
      } else if (e.type === "done") {
        setRunning(false);
      }
    });
  }

  const speedup =
    cerebras.done && baseline.done && cerebras.elapsedMs > 0
      ? baseline.elapsedMs / cerebras.elapsedMs
      : null;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <button
          disabled={running}
          onClick={run}
          className="rounded-lg bg-gradient-to-r from-accent to-cerebras px-4 py-2 text-sm font-bold text-white transition hover:brightness-110 disabled:opacity-50"
        >
          {running ? "Racing..." : "Run the same root-cause prompt on both"}
        </button>
        {speedup && (
          <div className="rounded-lg border border-ok/40 bg-ok/10 px-3 py-2 text-sm font-bold text-ok">
            Cerebras finished ~{speedup.toFixed(1)}x faster
          </div>
        )}
        <div className="ml-auto text-[11px] text-slate-500">
          Same prompt, streamed live. Baseline is a representative GPU host
          {cfg?.baseline_simulated ? " (simulated rate)" : ""}.
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Pane
          title={cfg?.cerebras_simulated ? "Gemma 4 31B - Cerebras (sim)" : "Gemma 4 31B - Cerebras"}
          subtitle="Wafer-scale inference"
          accent="text-cerebras"
          state={cerebras}
          winner={!!speedup}
        />
        <Pane
          title={cfg?.baseline_label ?? "GPU baseline"}
          subtitle="Typical GPU token rate"
          accent="text-slate-300"
          state={baseline}
          winner={false}
        />
      </div>
    </div>
  );
}
