import { useEffect, useState } from "react";
import { getConfig, type AppConfig } from "./lib/api";
import IncidentConsole from "./components/IncidentConsole";
import SpeedCompare from "./components/SpeedCompare";

type Tab = "warroom" | "speed";

function Badge({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-edge bg-panel px-3 py-1.5">
      <span className="text-[11px] uppercase tracking-wide text-slate-500">{label}</span>
      <span className={`text-xs font-semibold ${tone ?? "text-slate-200"}`}>{value}</span>
    </div>
  );
}

export default function App() {
  const [tab, setTab] = useState<Tab>("warroom");
  const [cfg, setCfg] = useState<AppConfig | null>(null);

  useEffect(() => {
    getConfig().then(setCfg).catch(() => setCfg(null));
  }, []);

  return (
    <div className="min-h-full">
      <header className="sticky top-0 z-10 border-b border-edge bg-ink/80 backdrop-blur">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center gap-3 px-5 py-3">
          <div className="flex items-center gap-2.5">
            <div className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-accent to-cerebras font-black text-white">
              C
            </div>
            <div>
              <div className="text-lg font-bold leading-none">CereMind</div>
              <div className="text-[11px] text-slate-500">
                Agentic incident response - Gemma 4 on Cerebras
              </div>
            </div>
          </div>

          <div className="ml-auto flex flex-wrap items-center gap-2">
            {cfg && (
              <>
                <Badge
                  label="Engine"
                  value={cfg.cerebras_simulated ? "gemma-4-31b (sim)" : cfg.cerebras_model}
                  tone="text-cerebras"
                />
                <Badge label="Embed" value={cfg.embedding_backend} />
                <Badge label="Vectors" value={cfg.vector_backend} />
                <Badge label="Pipeline" value={cfg.pipeline_backend} />
              </>
            )}
          </div>
        </div>

        <div className="mx-auto flex max-w-[1400px] gap-1 px-5">
          {(["warroom", "speed"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`rounded-t-lg px-4 py-2 text-sm font-medium transition ${
                tab === t
                  ? "bg-panel text-white"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              {t === "warroom" ? "War Room" : "Cerebras vs GPU"}
            </button>
          ))}
        </div>
      </header>

      <main className="mx-auto max-w-[1400px] px-5 py-5">
        {tab === "warroom" ? <IncidentConsole cfg={cfg} /> : <SpeedCompare cfg={cfg} />}
      </main>
    </div>
  );
}
