import { useRef, useState } from "react";
import { snapshotUrl } from "../lib/api";
import { Eye, Image } from "./icons";

// Shows the alert-carried snapshot (read by Gemma 4 vision) as a "vision panel"
// with a scanning overlay + corner frame, and lets an engineer optionally drop
// their own screenshot before a manual investigation.
export default function ScreenshotDrop({
  onPick,
  disabled,
  src,
}: {
  onPick: (dataUri: string | undefined) => void;
  disabled?: boolean;
  src?: string;
}) {
  const [preview, setPreview] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  function handleFile(file?: File) {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const uri = reader.result as string;
      setPreview(uri);
      onPick(uri);
    };
    reader.readAsDataURL(file);
  }

  const imgSrc = preview ?? src ?? snapshotUrl;

  return (
    <div className="glass overflow-hidden">
      <div className="flex items-center justify-between border-b border-edge/70 px-4 py-3">
        <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-wider text-accent2">
          <Eye className="h-4 w-4" /> Vision snapshot
        </div>
        <button
          disabled={disabled}
          onClick={() => inputRef.current?.click()}
          className="text-[11px] font-medium text-accent2 transition hover:text-accent disabled:opacity-40"
        >
          Upload my screenshot
        </button>
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e) => handleFile(e.target.files?.[0])}
        />
      </div>
      <div className="p-3">
        <div className="group relative overflow-hidden rounded-xl border border-edge bg-black/40 ring-1 ring-inset ring-accent/10">
          <img src={imgSrc} alt="pipeline snapshot" className="w-full" />

          {/* vision overlay: reading pill + corner frame + scan line */}
          <div className="pointer-events-none absolute left-3 top-3 flex items-center gap-1.5 rounded-md border border-accent/40 bg-ink/80 px-2 py-1 text-[10px] font-bold uppercase tracking-wider text-accent2 backdrop-blur">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent2 shadow-cyanGlow" />
            Gemma 4 vision - reading
          </div>
          <Frame />
          <div className="scanline" />
        </div>
        <div className="mt-2.5 flex items-center gap-1.5 text-[11.5px] text-muted">
          <Image className="h-3.5 w-3.5 text-accent2" />
          Gemma 4 vision reads this DAG/build dashboard to drive triage.
        </div>
      </div>
    </div>
  );
}

function Frame() {
  const c = "absolute h-5 w-5 border-accent/70";
  return (
    <div className="pointer-events-none absolute inset-3">
      <div className={`${c} left-0 top-0 border-l-2 border-t-2`} />
      <div className={`${c} right-0 top-0 border-r-2 border-t-2`} />
      <div className={`${c} bottom-0 left-0 border-b-2 border-l-2`} />
      <div className={`${c} bottom-0 right-0 border-b-2 border-r-2`} />
    </div>
  );
}
