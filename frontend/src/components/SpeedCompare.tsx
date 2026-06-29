import { useRef, useState } from "react";
import { streamSpeed, type AppConfig, type SpeedEvent } from "../lib/api";
import { Bolt, Play } from "./icons";

interface PaneState {
  text: string;
  tokens: number;
  tps: number;
  elapsedMs: number;
  done: boolean;
}
const EMPTY: PaneState = { text: "", tokens: 0, tps: 0, elapsedMs: 0, done: false };

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

      <div className="mt-4 grid grid-cols-3 gap-2">
        <Stat label="tokens/sec" value={state.tps ? state.tps.toFixed(0) : "-"} accent={accent} />
        <Stat label="elapsed" value={`${(state.elapsedMs / 1000).toFixed(2)}s`} />
        <Stat label="tokens" value={`${state.tokens}`} />
      </div>

      <div className="relative mt-4 min-h-[160px] flex-1 overflow-hidden rounded-xl border border-edge bg-ink/70 p-3.5 font-mono text-[12.5px] leading-relaxed text-slate-300">
        {state.text || <span className="text-muted">waiting...</span>}
        {!state.done && state.text && (
          <span className="ml-0.5 inline-block w-2 animate-blink bg-current align-middle">&nbsp;</span>
        )}
      </div>
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
      <div className="glass mb-5 flex flex-wrap items-center gap-3 p-4">
        <button disabled={running} onClick={run} className="btn-primary">
          {running ? (
            <>
              <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white" />
              Racing...
            </>
          ) : (
            <>
              <Play className="h-4 w-4" /> Run the same prompt on both
            </>
          )}
        </button>
        {speedup && (
          <div className="pill border-ok/40 bg-ok/15 px-3 py-2 text-sm font-bold text-ok">
            <Bolt className="h-4 w-4" /> Cerebras ~{speedup.toFixed(1)}x faster
          </div>
        )}
        <div className="ml-auto max-w-sm text-right text-[11px] leading-relaxed text-muted">
          Same root-cause prompt, streamed live. Baseline is a representative GPU host
          {cfg?.baseline_simulated ? " (simulated rate)" : ""}.
        </div>
      </div>

      <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
        <Pane
          title={cfg?.cerebras_simulated ? "Gemma 4 31B - Cerebras (sim)" : "Gemma 4 31B - Cerebras"}
          subtitle="Wafer-scale inference"
          accent="text-cerebras"
          ring="shadow-[0_0_0_1px_rgba(52,211,153,0.5),0_24px_60px_-24px_rgba(52,211,153,0.5)]"
          state={cerebras}
          winner={!!speedup}
        />
        <Pane
          title={cfg?.baseline_label ?? "GPU baseline"}
          subtitle="Typical GPU token rate"
          accent="text-slate-300"
          ring=""
          state={baseline}
          winner={false}
        />
      </div>
    </div>
  );
}
