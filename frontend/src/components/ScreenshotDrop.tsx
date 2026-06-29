import { useRef, useState } from "react";
import { snapshotUrl } from "../lib/api";
import { Eye, Image } from "./icons";

// Shows the alert-carried snapshot (read by Gemma 4 vision) and lets an engineer
// optionally drop their own screenshot before a manual investigation.
export default function ScreenshotDrop({
  onPick,
  disabled,
}: {
  onPick: (dataUri: string | undefined) => void;
  disabled?: boolean;
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

  return (
    <div className="glass overflow-hidden">
      <div className="flex items-center justify-between border-b border-edge/70 px-4 py-3">
        <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-wider text-slate-300">
          <Image className="h-4 w-4 text-cerebras" /> Alert snapshot
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
        <div className="overflow-hidden rounded-xl border border-edge ring-1 ring-inset ring-white/5">
          <img src={preview ?? snapshotUrl} alt="pipeline snapshot" className="w-full" />
        </div>
        <div className="mt-2.5 flex items-center gap-1.5 text-[11.5px] text-muted">
          <Eye className="h-3.5 w-3.5 text-cerebras" />
          Gemma 4 vision reads this DAG/build snapshot to drive triage.
        </div>
      </div>
    </div>
  );
}
