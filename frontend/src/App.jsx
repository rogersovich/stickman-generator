import { useEffect, useState } from "react";
import { AlertTriangle, ArrowLeft, Check, Clapperboard, Cloud, Copy, Settings as SettingsIcon, X } from "lucide-react";
import { api } from "./api.js";
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
  const [, projectId, step = "images"] = path.match(/^\/project\/([a-z0-9-]+)(?:\/(images|audio|export))?/) ?? [];
  const onSettings = path.startsWith("/settings");
  const [storage, setStorage] = useState(null);
  const [showBackupModal, setShowBackupModal] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const fetchStorage = () => api.storageStatus().then(setStorage).catch(() => {});
    fetchStorage();
    const interval = setInterval(fetchStorage, 15000);
    return () => clearInterval(interval);
  }, [path]);

  const handleCopyRclone = () => {
    if (storage?.rclone_backup_command) {
      navigator.clipboard.writeText(storage.rclone_backup_command);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

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

        <div className="flex items-center gap-2.5">
          {/* Status Indikator Cloud / Backup Pill */}
          {storage && (
            <>
              {storage.needs_backup ? (
                <button
                  onClick={() => setShowBackupModal(true)}
                  className="flex items-center gap-1.5 rounded-lg border border-amber-500/50 bg-amber-500/15 px-3 py-1.5 text-xs font-semibold text-amber-300 animate-pulse hover:bg-amber-500/25 transition shadow-sm"
                  title="30 Proyek tercapai. Waktunya backup ke Google Drive via rclone!"
                >
                  <AlertTriangle size={14} className="text-amber-400" />
                  <span>Waktunya Backup ({storage.total_projects}/{storage.backup_threshold})</span>
                </button>
              ) : (
                <div
                  className="hidden sm:flex items-center gap-2 rounded-lg border border-[#292e3b] bg-[#161920] px-2.5 py-1 text-[11px] font-mono text-slate-400 cursor-pointer hover:border-[#3d4455] transition"
                  onClick={() => go("/settings")}
                  title={`Cloud D1 & R2 aktif. ${storage.total_projects}/${storage.backup_threshold} proyek. Kapasitas: ${storage.r2_stats?.used_mb ?? 0} MB / 10 GB`}
                >
                  <Cloud size={13} className="text-emerald-400" />
                  <span>{storage.total_projects}/{storage.backup_threshold} Proyek</span>
                  <span className="text-slate-600">·</span>
                  <span className="text-slate-300">{storage.r2_stats?.used_mb ?? 0} MB</span>
                </div>
              )}
            </>
          )}

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
        </div>
      </header>

      {/* Modal Dialog Backup Google Drive & Rclone */}
      {showBackupModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="w-full max-w-lg rounded-2xl border border-amber-500/40 bg-[#161920] p-6 shadow-2xl space-y-4">
            <div className="flex items-start justify-between gap-3 border-b border-[#292e3b] pb-3">
              <div className="flex items-center gap-2 text-amber-400">
                <AlertTriangle size={20} />
                <h3 className="text-base font-bold text-slate-100">Waktunya Backup ke Google Drive</h3>
              </div>
              <button
                onClick={() => setShowBackupModal(false)}
                className="text-slate-400 hover:text-slate-200 p-1"
              >
                <X size={18} />
              </button>
            </div>

            <div className="space-y-3 text-xs text-slate-300 leading-relaxed">
              <p>
                Jumlah proyek di Cloudflare R2 telah mencapai <b>{storage?.total_projects} proyek</b> (batas aman rekomendasi: {storage?.backup_threshold} proyek).
              </p>
              <p className="text-slate-400">
                Karena proyek-proyek ini umumnya sudah selesai di-render dan diunggah ke YouTube, disarankan memindahkan arsipnya ke Google Drive (khusus akun: <b className="text-amber-300 font-mono">{storage?.gdrive_email || "aseplandak02@gmail.com"}</b>) via <b>rclone</b> agar kuota 10 GB gratis Cloudflare R2 selalu aman dan bersih.
              </p>

              <div className="space-y-1.5 pt-1">
                <span className="font-mono text-[11px] text-amber-300 font-semibold">Perintah Backup Rclone Terminal:</span>
                <div className="relative">
                  <pre className="rounded-lg border border-[#292e3b] bg-[#0e1015] p-3 font-mono text-[11px] text-amber-200/90 whitespace-pre-wrap break-all pr-12">
                    {storage?.rclone_backup_command}
                  </pre>
                  <button
                    onClick={handleCopyRclone}
                    className="absolute top-2 right-2 rounded-md bg-[#1e222b] p-1.5 text-slate-300 hover:text-amber-400 transition"
                    title="Salin Perintah"
                  >
                    {copied ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
                  </button>
                </div>
              </div>

              <div className="rounded-lg border border-[#292e3b] bg-[#12141a] p-3 text-[11px] text-slate-400 space-y-1">
                <p><b>Cara Jalankan:</b></p>
                <ul className="list-disc pl-4 space-y-0.5">
                  <li><b>Windows:</b> Cukup klik 2x file <code className="text-amber-300">backup.bat</code> di folder utama proyek!</li>
                  <li><b>Mac:</b> Buka Terminal di folder proyek lalu jalankan <code className="text-amber-300">./backup.sh</code>.</li>
                  <li>Atau salin perintah baris rclone di atas langsung ke terminal kamu.</li>
                </ul>
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-[#292e3b]">
              <button
                className="btn-primary py-1.5 px-4 text-xs"
                onClick={() => setShowBackupModal(false)}
              >
                Tutup & Nanti Saja
              </button>
            </div>
          </div>
        </div>
      )}

      <main>
        {onSettings ? (
          <Settings />
        ) : projectId ? (
          <ProjectPage key={projectId} id={projectId} step={step} />
        ) : (
          <Home />
        )}
      </main>
    </div>
  );
}
