import { useEffect, useState } from "react";
import { ArrowLeft, Clapperboard, Settings as SettingsIcon } from "lucide-react";
import Home from "./Home.jsx";
import ProjectPage from "./ProjectPage.jsx";
import Settings from "./Settings.jsx";

function useHashRoute() {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const onChange = () => setHash(window.location.hash);
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return hash;
}

export function go(path) {
  window.location.hash = path;
}

export default function App() {
  const hash = useHashRoute();
  const projectId = hash.match(/^#\/p\/([a-z0-9-]+)/)?.[1];
  const onSettings = hash.startsWith("#/settings");

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <header className="mb-8 flex items-center justify-between border-b border-[#292e3b] pb-4">
        <div className="flex items-center gap-3">
          {(projectId || onSettings) && (
            <button
              onClick={() => go("/")}
              className="btn-ghost px-3 py-1.5 text-xs text-slate-300"
              aria-label="Kembali ke menu utama"
            >
              <ArrowLeft size={14} /> Beranda
            </button>
          )}
          <button
            onClick={() => go("/")}
            className="group flex items-center gap-2.5 text-left text-base font-bold tracking-tight text-slate-100 transition-colors focus-visible:outline-none"
          >
            <div className="flex size-7 items-center justify-center rounded-lg border border-amber-500/40 bg-amber-500/10 text-amber-400 shadow-2xs group-hover:border-amber-400 group-hover:bg-amber-500/20">
              <Clapperboard size={15} />
            </div>
            <span className="flex items-center gap-2">
              STICKMAN GENERATOR
              <span className="rounded-md border border-[#292e3b] bg-[#161920] px-1.5 py-0.5 font-mono text-[10px] font-medium tracking-normal text-slate-400">
                STUDIO
              </span>
            </span>
          </button>
        </div>

        <button
          onClick={() => go("/settings")}
          className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors ${
            onSettings
              ? "border-amber-500/50 bg-amber-500/10 text-amber-300"
              : "border-[#292e3b] bg-[#161920] text-slate-400 hover:border-[#3d4455] hover:text-slate-200"
          }`}
          aria-label="Pengaturan Studio"
          title="Pengaturan"
        >
          <SettingsIcon size={14} className={onSettings ? "text-amber-400" : "text-slate-400"} />
          <span>Pengaturan</span>
        </button>
      </header>

      <main>
        {onSettings ? (
          <Settings />
        ) : projectId ? (
          <ProjectPage key={projectId} id={projectId} />
        ) : (
          <Home />
        )}
      </main>
    </div>
  );
}
