import { useEffect, useState } from "react";
import { getConfig, type AppConfig } from "./lib/api";
import IncidentConsole from "./components/IncidentConsole";
import SpeedCompare from "./components/SpeedCompare";
import { Activity, Bolt, Shield, Sparkle } from "./components/icons";

type Tab = "warroom" | "speed";

function Badge({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex items-center gap-1.5 rounded-lg border border-edge bg-panel/60 px-2.5 py-1.5 backdrop-blur">
      <span className="text-[10px] font-medium uppercase tracking-wider text-muted">{label}</span>
      <span className={`text-xs font-semibold ${tone ?? "text-slate-100"}`}>{value}</span>
    </div>
  );
}

export default function App() {
  const [tab, setTab] = useState<Tab>("warroom");
  const [cfg, setCfg] = useState<AppConfig | null>(null);

  useEffect(() => {
    getConfig().then(setCfg).catch(() => setCfg(null));
  }, []);

  const live = cfg && !cfg.cerebras_simulated;

  return (
    <div className="min-h-full bg-grid-faint bg-[size:44px_44px]">
      <header className="sticky top-0 z-20 border-b border-edge/70 bg-ink/70 backdrop-blur-xl">
        <div className="mx-auto flex max-w-[1440px] flex-wrap items-center gap-4 px-6 py-3.5">
          <div className="flex items-center gap-3">
            <div className="relative grid h-10 w-10 place-items-center rounded-2xl bg-gradient-to-br from-accent via-accent2 to-cerebras shadow-[0_8px_24px_-8px_rgba(124,92,255,0.9)]">
              <Bolt className="h-5 w-5 text-white" />
            </div>
            <div>
              <div className="flex items-center gap-2 text-[19px] font-extrabold leading-none tracking-tight">
                CereMind
                <span className="pill border-accent/30 bg-accent/10 text-accent2">
                  <Sparkle className="h-3 w-3" /> agentic SRE
                </span>
              </div>
              <div className="mt-1 text-[11px] text-muted">
                Autonomous incident response - Gemma 4 31B on Cerebras
              </div>
            </div>
          </div>

          <div className="ml-auto flex flex-wrap items-center gap-2">
            <div
              className={`flex items-center gap-2 rounded-lg border px-2.5 py-1.5 ${
                live
                  ? "border-ok/30 bg-ok/10 text-ok"
                  : "border-warn/30 bg-warn/10 text-warn"
              }`}
            >
              <span className="relative flex h-2 w-2">
                <span className="dot live h-2 w-2 bg-current" />
              </span>
              <span className="text-xs font-semibold">{live ? "Live Cerebras" : "Simulated"}</span>
            </div>
            {cfg && (
              <>
                <Badge
                  label="model"
                  value={cfg.cerebras_model}
                  tone="text-cerebras"
                />
                <Badge label="embed" value={cfg.embedding_backend} />
                <Badge label="vectors" value={cfg.vector_backend} />
                <Badge label="pipeline" value={cfg.pipeline_backend} />
              </>
            )}
          </div>
        </div>

        <div className="mx-auto flex max-w-[1440px] gap-1 px-6">
          <Tab
            active={tab === "warroom"}
            onClick={() => setTab("warroom")}
            icon={<Activity className="h-4 w-4" />}
            label="War Room"
          />
          <Tab
            active={tab === "speed"}
            onClick={() => setTab("speed")}
            icon={<Bolt className="h-4 w-4" />}
            label="Cerebras vs GPU"
          />
          <div className="ml-auto hidden items-center gap-1.5 self-center pb-2 text-[11px] text-muted sm:flex">
            <Shield className="h-3.5 w-3.5" /> read-only by default - writes gated by approval
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1440px] px-6 py-6">
        {tab === "warroom" ? <IncidentConsole cfg={cfg} /> : <SpeedCompare cfg={cfg} />}
      </main>
    </div>
  );
}

function Tab({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      className={`relative flex items-center gap-2 rounded-t-xl px-4 py-2.5 text-sm font-semibold transition ${
        active ? "text-white" : "text-muted hover:text-slate-200"
      }`}
    >
      {icon}
      {label}
      {active && (
        <span className="absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-gradient-to-r from-accent to-cerebras" />
      )}
    </button>
  );
}
