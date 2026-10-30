import { useEffect, useState } from "react";
import { Loader2, Trash2 } from "lucide-react";
import { api } from "./api.js";
import { go } from "./App.jsx";
import { confirmDelete } from "./deleteProject.js";
import { useDialog } from "./ui.jsx";
import DraftEditor from "./DraftEditor.jsx";
import ProgressView from "./ProgressView.jsx";
import ProjectSteps from "./ProjectSteps.jsx";

export default function ProjectPage({ id, step }) {
  const dialog = useDialog();
  const [project, setProject] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.project(id).then(setProject).catch((e) => setError(e.message));
  }, [id]);

  if (error) {
    return (
      <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-5 text-sm text-red-300">
        <p className="font-semibold">Gagal memuat project:</p>
        <p className="mt-1 font-mono text-xs">{error}</p>
        <button onClick={() => go("/")} className="btn-ghost mt-4 text-xs">
          Kembali ke Beranda
        </button>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="flex items-center justify-center py-20 text-slate-400 gap-2.5 font-mono text-sm">
        <Loader2 size={18} className="animate-spin text-amber-400" />
        <span>Memuat data project…</span>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <span className="font-mono text-xs text-slate-400">
          ID: <span className="text-slate-300">{project.id}</span>
        </span>
        <button
          className="btn-danger py-1 px-2.5 text-xs"
          onClick={async () => (await confirmDelete(project, dialog)) && go("/")}
          title="Hapus seluruh project ini"
        >
          <Trash2 size={13} /> Hapus Project
        </button>
      </div>

      {project.status === "draft" ? (
        <DraftEditor project={project} onConfirmed={setProject} />
      ) : (
        <>
          <ProjectSteps project={project} step={step} />
          {step === "audio" ? (
            <div className="panel p-6 text-sm text-slate-400">Halaman audio sedang disiapkan.</div>
          ) : step === "export" ? (
            <div className="panel p-6 text-sm text-slate-400">Review + Export CapCut segera hadir.</div>
          ) : (
            <ProgressView project={project} setProject={setProject} />
          )}
        </>
      )}
    </div>
  );
}
