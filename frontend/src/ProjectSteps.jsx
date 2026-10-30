import { AudioLines, Clapperboard, Image } from "lucide-react";
import { go } from "./App.jsx";

// Step bar of a project: 1 Gambar → 2 Audio → 3 Export, each with its own URL.
export default function ProjectSteps({ project, step }) {
  const total = project.scenes.length;
  const imagesDone = project.scenes.filter((s) => s.image_status === "done").length;
  const audioDone = project.scenes.filter((s) => s.audio_status === "done" && !s.audio_stale).length;
  const stale = project.scenes.filter((s) => s.audio_stale).length;

  const steps = [
    { key: "images", n: 1, label: "Gambar", icon: Image, meta: `${imagesDone}/${total}` },
    { key: "audio", n: 2, label: "Audio", icon: AudioLines, meta: `${audioDone}/${total}`, warn: stale ? `${stale} basi` : null },
    { key: "export", n: 3, label: "Export", icon: Clapperboard, meta: "Segera", disabled: true },
  ];

  return (
    <nav className="mb-5 grid grid-cols-3 gap-1 rounded-xl border border-[#292e3b] bg-[#161920] p-1" aria-label="Langkah project">
      {steps.map(({ key, n, label, icon: Icon, meta, warn, disabled }) => {
        const active = step === key;
        return (
          <button
            key={key}
            disabled={disabled}
            aria-current={active ? "step" : undefined}
            onClick={() => go(`/project/${project.id}/${key}`)}
            className={`flex min-w-0 items-center justify-center gap-2 rounded-lg px-2 py-2.5 text-xs transition sm:text-sm ${
              active
                ? "bg-amber-500/15 font-semibold text-amber-300"
                : disabled
                ? "cursor-not-allowed text-slate-500"
                : "text-slate-400 hover:bg-[#1e222b] hover:text-slate-200"
            }`}
          >
            <Icon size={15} className="shrink-0" />
            <span className="truncate">
              {n} · {label}
            </span>
            <span className="hidden font-mono text-[11px] text-slate-500 sm:inline">{meta}</span>
            {warn && <span className="hidden rounded bg-amber-500/15 px-1.5 font-mono text-[10px] text-amber-300 sm:inline">{warn}</span>}
          </button>
        );
      })}
    </nav>
  );
}
