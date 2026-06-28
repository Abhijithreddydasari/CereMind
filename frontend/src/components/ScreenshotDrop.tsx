import { useRef, useState } from "react";
import { snapshotUrl } from "../lib/api";

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
    <div className="rounded-xl border border-edge bg-panel p-3">
      <div className="mb-2 flex items-center justify-between">
        <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">
          Alert snapshot (multimodal input)
        </div>
        <button
          disabled={disabled}
          onClick={() => inputRef.current?.click()}
          className="text-[11px] text-accent hover:underline disabled:opacity-40"
        >
          Replace with my screenshot
        </button>
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e) => handleFile(e.target.files?.[0])}
        />
      </div>
      <img
        src={preview ?? snapshotUrl}
        alt="pipeline snapshot"
        className="w-full rounded-lg border border-edge"
      />
      <div className="mt-2 text-[11px] text-slate-500">
        Gemma 4 vision reads this DAG/build snapshot as part of the investigation.
      </div>
    </div>
  );
}
