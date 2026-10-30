import { useEffect, useState } from "react";
import { ArrowLeft, Clapperboard, Settings as SettingsIcon } from "lucide-react";
import Home from "./Home.jsx";
import ProjectPage from "./ProjectPage.jsx";
import Settings from "./Settings.jsx";

// Old links (bookmarks, extension notifications) used "#/p/<id>" and "#/settings": rewrite them once
const legacy = window.location.hash.match(/^#(\/.*)$/)?.[1];
if (legacy) window.history.replaceState(null, "", legacy.replace(/^\/p\//, "/project/"));

function usePathRoute() {
  const [path, setPath] = useState(window.location.pathname);
  useEffect(() => {
    const onChange = () => setPath(window.location.pathname);
    window.addEventListener("popstate", onChange);
    return () => window.removeEventListener("popstate", onChange);
  }, []);
  return path;
}

export function go(path) {
  if (path === window.location.pathname) return;
  window.history.pushState(null, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
  window.scrollTo(0, 0);
}

export default function App() {
  const path = usePathRoute();
  const projectId = path.match(/^\/project\/([a-z0-9-]+)/)?.[1];
  const onSettings = path.startsWith("/settings");

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
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
