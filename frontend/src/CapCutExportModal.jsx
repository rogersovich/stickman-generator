import { Dialog, DialogBackdrop, DialogPanel, DialogTitle } from "@headlessui/react";
import {
  AlertCircle,
  Check,
  CheckCircle2,
  Copy,
  Film,
  FolderCheck,
  Image as ImageIcon,
  Loader2,
  Music,
  Sliders,
  Sparkles,
  X,
} from "lucide-react";
import { useState } from "react";
import { api } from "./api.js";
import { Toggle } from "./ui.jsx";

export default function CapCutExportModal({ open, onClose, project, onExported }) {
  const [projectName, setProjectName] = useState(project.title || project.id);
  const [kenBurns, setKenBurns] = useState(true);
  const [transitions, setTransitions] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [copied, setCopied] = useState(false);

  const scenes = project.scenes;
  const total = scenes.length;
  const imagesDone = scenes.filter((s) => s.image_status === "done").length;
  const audioDone = scenes.filter((s) => s.audio_status === "done" && !s.audio_stale).length;

  const totalAudioSec = scenes.reduce(
    (sum, s) => sum + (s.audio_status === "done" ? s.audio_duration ?? 0 : (s.image_status === "done" ? 2.5 : 0)),
    0
  );
  const totalMin = Math.floor(totalAudioSec / 60);
  const totalRemSec = Math.round(totalAudioSec % 60);

  function handleClose() {
    if (exporting) return;
    setError(null);
    setResult(null);
    onClose();
  }

  async function handleExport() {
    setExporting(true);
    setError(null);
    try {
      const res = await api.exportCapCut(project.id, {
        project_name: projectName.trim() || project.title || project.id,
        ken_burns: kenBurns,
        zoom_ratio: 1.15,
        enable_transitions: transitions,
        transition_duration: 0.5,
      });
      setResult(res);
      onExported?.(res);
    } catch (e) {
      setError(e.message || "Gagal mengekspor draft CapCut");
    } finally {
      setExporting(false);
    }
  }

  function copyPath() {
    if (!result?.draft_path) return;
    navigator.clipboard.writeText(result.draft_path);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  }

  return (
    <Dialog open={open} onClose={handleClose} className="relative z-50">
      <DialogBackdrop transition className="fixed inset-0 bg-black/75 backdrop-blur-xs duration-150 data-closed:opacity-0" />
      <div className="fixed inset-0 flex items-center justify-center p-4">
        <DialogPanel
          transition
          className="flex max-h-[90vh] w-full max-w-xl flex-col gap-4 rounded-2xl border border-[#292e3b] bg-[#161920] p-6 shadow-2xl duration-150 data-closed:scale-95 data-closed:opacity-0"
        >
          {result ? (
            /* --- SUCCESS VIEW --- */
            <div className="space-y-5 py-2">
              <div className="flex items-center gap-3.5">
                <div className="flex size-11 shrink-0 items-center justify-center rounded-2xl border border-emerald-500/30 bg-emerald-500/10 text-emerald-400 shadow-lg shadow-emerald-500/10">
                  <CheckCircle2 size={24} />
                </div>
                <div>
                  <DialogTitle className="text-lg font-bold text-slate-100">
                    Draft CapCut Berhasil Dibuat!
                  </DialogTitle>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Proyek timeline otomatis dibuat dan siap diedit di aplikasi CapCut Desktop.
                  </p>
                </div>
              </div>

              {/* Structured Result Info */}
              <div className="rounded-xl border border-[#292e3b] bg-[#12141a] p-4 space-y-3">
                <div className="flex items-center justify-between border-b border-[#292e3b] pb-2.5">
                  <span className="text-xs text-slate-400 font-medium">Nama Proyek:</span>
                  <span className="font-semibold text-sm text-amber-300 font-mono truncate max-w-[280px]">
                    {result.draft_name}
                  </span>
                </div>
                <div className="grid grid-cols-3 gap-2 py-1 text-center font-mono">
                  <div className="rounded-lg bg-[#181c24] p-2 border border-[#292e3b]/60">
                    <div className="text-[11px] text-slate-400">Gambar</div>
                    <div className="text-base font-bold text-slate-100">{result.exported_images}</div>
                  </div>
                  <div className="rounded-lg bg-[#181c24] p-2 border border-[#292e3b]/60">
                    <div className="text-[11px] text-slate-400">Audio WAV</div>
                    <div className="text-base font-bold text-slate-100">{result.exported_audios}</div>
                  </div>
                  <div className="rounded-lg bg-[#181c24] p-2 border border-[#292e3b]/60">
                    <div className="text-[11px] text-slate-400">Durasi</div>
                    <div className="text-base font-bold text-amber-300">~{result.total_duration_s}s</div>
                  </div>
                </div>

                <div className="pt-2">
                  <div className="flex items-center justify-between text-xs text-slate-400 mb-1.5">
                    <span>Lokasi Folder Draft:</span>
                    <button
                      onClick={copyPath}
                      className="flex items-center gap-1 text-[11px] text-amber-400 hover:text-amber-300 transition"
                    >
                      {copied ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}
                      {copied ? "Tersalin!" : "Salin Path"}
                    </button>
                  </div>
                  <div className="rounded-lg bg-[#0d0f14] p-2.5 font-mono text-[11px] text-slate-300 break-all select-all border border-[#222733]">
                    {result.draft_path}
                  </div>
                </div>
              </div>

              {/* Step Guide */}
              <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-3.5 text-xs text-emerald-200/90 leading-relaxed flex items-start gap-2.5">
                <Sparkles size={16} className="text-emerald-400 shrink-0 mt-0.5" />
                <div>
                  <b>Langkah Selanjutnya:</b> Buka aplikasi <b>CapCut Desktop</b> di komputer Anda. Proyek <b>"{result.draft_name}"</b> sudah langsung berada di daftar project teratas dan siap dibuka!
                </div>
              </div>

              <div className="flex justify-end pt-2">
                <button
                  className="btn-primary px-5 py-2 text-sm"
                  onClick={handleClose}
                >
                  Selesai
                </button>
              </div>
            </div>
          ) : (
            /* --- FORM / SETTINGS VIEW --- */
            <>
              {/* Header */}
              <div className="flex items-start justify-between gap-3 border-b border-[#292e3b] pb-3">
                <div className="flex items-center gap-3">
                  <div className="flex size-10 items-center justify-center rounded-xl border border-amber-500/30 bg-amber-500/10 text-amber-400">
                    <Film size={20} />
                  </div>
                  <div>
                    <DialogTitle className="text-base font-bold text-slate-100">
                      Konfirmasi Ekspor ke CapCut Desktop
                    </DialogTitle>
                    <p className="mt-0.5 text-xs text-slate-400">
                      Rakit seluruh adegan dan klip audio narasi menjadi draft timeline CapCut.
                    </p>
                  </div>
                </div>
                <button
                  className="rounded-lg p-1.5 text-slate-400 hover:bg-[#1e222b] hover:text-slate-200"
                  onClick={handleClose}
                  aria-label="Tutup"
                >
                  <X size={18} />
                </button>
              </div>

              {/* Body */}
              <div className="space-y-4 py-1">
                {/* Project Name Field */}
                <div className="space-y-1.5">
                  <label className="label mb-0">Nama Proyek di CapCut</label>
                  <input
                    className="input font-medium"
                    value={projectName}
                    onChange={(e) => setProjectName(e.target.value)}
                    placeholder="Nama project CapCut…"
                    maxLength={100}
                  />
                  <p className="text-[11px] text-slate-500">
                    Akan otomatis ditambahkan stempel waktu agar tidak menimpa draft sebelumnya.
                  </p>
                </div>

                {/* Summary Badges */}
                <div className="grid grid-cols-3 gap-2.5 rounded-xl border border-[#292e3b] bg-[#12141a] p-3 text-xs">
                  <div className="space-y-1">
                    <span className="text-slate-500">Total Adegan</span>
                    <div className="font-semibold text-slate-200">{total} Adegan</div>
                  </div>
                  <div className="space-y-1">
                    <span className="text-slate-500">Kesiapan Aset</span>
                    <div className="font-semibold text-slate-200">
                      <span className="text-sky-400">{imagesDone} Gbr</span> • <span className="text-emerald-400">{audioDone} Aud</span>
                    </div>
                  </div>
                  <div className="space-y-1">
                    <span className="text-slate-500">Estimasi Durasi</span>
                    <div className="font-semibold text-amber-300 font-mono">
                      {totalMin}m {totalRemSec}d
                    </div>
                  </div>
                </div>

                {audioDone < total && (
                  <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200 flex items-start gap-2.5">
                    <AlertCircle size={15} className="shrink-0 text-amber-400 mt-0.5" />
                    <p className="leading-relaxed">
                      <b>Catatan:</b> Sebanyak {total - audioDone} adegan belum memiliki klip audio narasi. Adegan tersebut akan menggunakan durasi standar 2,5 detik di timeline CapCut.
                    </p>
                  </div>
                )}

                {/* Effects Settings Box */}
                <div className="rounded-xl border border-[#292e3b] bg-[#12141a]/60 p-4 space-y-3.5">
                  <div className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
                    <Sliders size={13} className="text-amber-400" /> Pengaturan Efek Timeline
                  </div>

                  <div className="space-y-3 pt-1">
                    <Toggle
                      checked={kenBurns}
                      onChange={setKenBurns}
                      label="Animasi Ken Burns (Zoom-in & Pan)"
                      desc="Menggerakkan kamera secara dinamis pada setiap gambar agar storyboard video tidak kaku."
                    />

                    <div className="border-t border-[#292e3b]/60 pt-3">
                      <Toggle
                        checked={transitions}
                        onChange={setTransitions}
                        label="Transisi Dinamis Antar-Adegan"
                        desc="Menerapkan efek transisi CapCut otomatis di setiap potongan gambar."
                      />
                    </div>
                  </div>
                </div>

                {error && (
                  <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300 flex items-center gap-2">
                    <AlertCircle size={15} className="shrink-0" />
                    <span>{error}</span>
                  </div>
                )}
              </div>

              {/* Footer */}
              <div className="flex items-center justify-end gap-2.5 border-t border-[#292e3b] pt-3.5">
                <button
                  type="button"
                  className="btn-ghost px-4 py-2 text-sm"
                  onClick={handleClose}
                  disabled={exporting}
                >
                  Batal
                </button>
                <button
                  type="button"
                  className="btn-primary px-5 py-2 text-sm font-semibold flex items-center gap-2 shadow-lg shadow-amber-500/20"
                  onClick={handleExport}
                  disabled={exporting || imagesDone === 0}
                >
                  {exporting ? <Loader2 size={15} className="animate-spin" /> : <Film size={15} />}
                  {exporting ? "Sedang Merakit Draft…" : "Mulai Ekspor ke CapCut"}
                </button>
              </div>
            </>
          )}
        </DialogPanel>
      </div>
    </Dialog>
  );
}
