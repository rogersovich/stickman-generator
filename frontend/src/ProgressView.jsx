import { useEffect, useState } from "react";
import { AlertTriangle, ArrowLeft, ArrowRight, ArrowRightLeft, ChevronLeft, ChevronRight, Clock, Columns2, Columns3, Columns4, Download, ExternalLink, FileArchive, Layers, Maximize2, Pause, Play, RotateCcw, Trash2, WandSparkles, X, Zap } from "lucide-react";
import { api } from "./api.js";
import FailedNav, { useFailedNav } from "./FailedNav.jsx";
import NarrationEditor from "./NarrationEditor.jsx";
import { useDialog } from "./ui.jsx";

// Frame grid layouts (full class strings so Tailwind picks them up); phones always get fewer columns
const GRID_COLS = {
  2: "sm:grid-cols-2",
  3: "sm:grid-cols-2 lg:grid-cols-3",
  4: "sm:grid-cols-3 lg:grid-cols-4",
};
const GRID_ICON = { 2: Columns2, 3: Columns3, 4: Columns4 };

// Column choice is remembered per format: 16:9 and 9:16 frames read best at different sizes
function useGridCols(format) {
  const key = `stickman.gridCols.${format}`;
  const fallback = format === "9:16" ? 4 : 2;
  const [cols, setCols] = useState(() => {
    try {
      const saved = Number(localStorage.getItem(key));
      return GRID_COLS[saved] ? saved : fallback;
    } catch {
      return fallback;
    }
  });
  const choose = (n) => {
    setCols(n);
    try {
      localStorage.setItem(key, String(n));
    } catch {}
  };
  return [cols, choose];
}

const BADGE = {
  pending: "bg-slate-800 text-slate-400 border border-slate-700/60",
  generating: "bg-amber-500/15 text-amber-300 border border-amber-500/40 animate-pulse",
  done: "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30",
  failed: "bg-red-500/15 text-red-300 border border-red-500/30",
};

function SceneNote({ scene }) {
  if (!scene.error) return null;
  const done = scene.image_status === "done";
  // a finished frame only warns when something went wrong (failed 2K download, low-res fallback)
  const warn = done && /gagal|rendah/i.test(scene.error);
  const tone = !done
    ? "border-red-500/30 bg-red-500/10 text-red-300"
    : warn
    ? "border-amber-500/30 bg-amber-500/10 text-amber-300"
    : "border-[#292e3b] bg-[#12141a] text-slate-400";
  return (
    <p className={`rounded-lg px-2.5 py-1.5 text-xs break-words border ${tone}`}>
      {warn && <AlertTriangle size={13} className="mr-1 inline -translate-y-px" />}
      {scene.error}
    </p>
  );
}

function Lightbox({ project, index, onClose, onNavigate, onRetry, onRedownload, onEditNarration }) {
  const scene = project.scenes[index];
  const [size, setSize] = useState(null);
  const count = project.scenes.length;
  const src = scene.image_file && api.fileUrl(project.id, scene.image_file, project.updated_at);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowRight") onNavigate((index + 1) % count);
      if (e.key === "ArrowLeft") onNavigate((index - 1 + count) % count);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [index, count, onClose, onNavigate]);

  useEffect(() => setSize(null), [index]);

  return (
    <div className="fixed inset-0 z-50 flex bg-black/90 backdrop-blur-md" onClick={onClose}>
      <div className="m-auto flex max-h-screen w-full max-w-6xl flex-col gap-5 overflow-y-auto p-4 md:flex-row md:items-center" onClick={(e) => e.stopPropagation()}>
        <div className="relative flex flex-1 items-center justify-center min-h-[50vh]">
          <button
            className="btn-ghost absolute left-2 z-10 size-10 rounded-full p-0 shadow-lg"
            onClick={() => onNavigate((index - 1 + count) % count)}
            aria-label="Scene sebelumnya"
          >
            <ChevronLeft size={22} />
          </button>

          {src ? (
            <img
              src={src}
              alt={`Scene ${index + 1}`}
              onLoad={(e) => setSize(`${e.target.naturalWidth}×${e.target.naturalHeight}`)}
              className="max-h-[85vh] max-w-full rounded-xl object-contain border border-[#292e3b] shadow-2xl"
            />
          ) : (
            <div className="flex aspect-video w-full max-w-lg items-center justify-center rounded-xl border border-dashed border-[#292e3b] bg-[#161920] text-sm text-slate-400">
              Belum ada gambar ({scene.image_status})
            </div>
          )}

          <button
            className="btn-ghost absolute right-2 z-10 size-10 rounded-full p-0 shadow-lg"
            onClick={() => onNavigate((index + 1) % count)}
            aria-label="Scene berikutnya"
          >
            <ChevronRight size={22} />
          </button>
        </div>

        <aside className="w-full space-y-4 rounded-2xl border border-[#292e3b] bg-[#161920] p-5 md:w-88 md:shrink-0">
          <div className="flex items-center justify-between border-b border-[#292e3b] pb-3">
            <span className="font-mono text-xs font-bold text-amber-400">
              FRAME {String(index + 1).padStart(2, "0")} / {String(count).padStart(2, "0")}
            </span>
            <button
              className="rounded-lg p-1 text-slate-400 hover:bg-[#1e222b] hover:text-white transition-colors"
              onClick={onClose}
              aria-label="Tutup lightbox"
            >
              <X size={18} />
            </button>
          </div>

          {scene.is_merged && (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-xs text-amber-200">
              [DUAL SPLIT-SCREEN] Digabung dengan Scene {(scene.merged_with ?? index - 1) + 1}
            </div>
          )}

          {scene.title_text && (
            <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-1.5">
              <span className="text-[10px] uppercase font-mono text-amber-400 block">Teks Judul</span>
              <p className="text-sm font-bold text-slate-100">{scene.title_text}</p>
            </div>
          )}

          <div>
            <p className="label">Beat Narasi Suara</p>
            <p className="text-sm leading-relaxed text-slate-200">{scene.narration}</p>
          </div>

          {scene.prompt ? (
            <details className="text-xs text-slate-400">
              <summary className="cursor-pointer select-none font-medium hover:text-slate-300">
                Prompt Lengkap Google Flow
              </summary>
              <pre className="mt-2 rounded-lg border border-[#292e3b] bg-[#12141a] p-2.5 font-mono text-[11px] leading-relaxed text-amber-200/80 max-h-48 overflow-y-auto whitespace-pre-wrap">
                {scene.prompt}
              </pre>
            </details>
          ) : (
            <details className="text-xs text-slate-400">
              <summary className="cursor-pointer select-none font-medium hover:text-slate-300">
                Visual Prompt Google Flow
              </summary>
              <p className="mt-2 rounded-lg border border-[#292e3b] bg-[#12141a] p-2.5 font-mono text-[11px] leading-relaxed text-amber-200/80">
                {scene.scene_description}
              </p>
            </details>
          )}

          <SceneNote scene={scene} />

          <div className="flex flex-wrap items-center gap-1.5 font-mono text-xs text-slate-400 pt-1">
            <span className={`rounded px-2 py-0.5 ${BADGE[scene.image_status]}`}>{scene.image_status}</span>
            {size && <span className="rounded border border-[#292e3b] bg-[#1e222b] px-2 py-0.5">{size} px</span>}
            {scene.needs_hd && (
              <span className="rounded border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-amber-300">
                low-res
              </span>
            )}
          </div>

          {scene.needs_hd && (
            <button className="btn-primary w-full py-2 text-xs" onClick={() => onRedownload(index)}>
              <Download size={14} /> Ambil 2K Full Resolution
            </button>
          )}

          <div className="grid grid-cols-2 gap-2 pt-2">
            <button className="btn-ghost text-xs" onClick={() => onEditNarration(index)}>
              <WandSparkles size={13} /> Ubah Narasi
            </button>
            {(scene.image_status === "done" || scene.image_status === "failed") && !scene.is_merged && (
              <button className="btn-ghost text-xs" onClick={() => onRetry(index)}>
                <RotateCcw size={13} /> {scene.image_status === "failed" ? "Coba Lagi" : "Generate Ulang"}
              </button>
            )}
            {src && (
              <>
                <a
                  className="btn-primary col-span-2 text-xs"
                  href={src}
                  download={`scene_${String(index + 1).padStart(3, "0")}.${scene.image_file?.split(".").pop() || "png"}`}
                >
                  <Download size={13} /> Unduh File Frame #{index + 1}
                </a>
                <a className="btn-ghost col-span-2 text-xs" href={src} target="_blank" rel="noreferrer">
                  <ExternalLink size={13} /> Buka Gambar di Tab Baru
                </a>
              </>
            )}
          </div>

          <p className="flex items-center justify-center gap-1.5 border-t border-[#292e3b] pt-3 text-[11px] text-slate-400 font-mono">
            <ArrowLeft size={11} /> <ArrowRight size={11} /> geser frame · Esc tutup
          </p>
        </aside>
      </div>
    </div>
  );
}

export default function ProgressView({ project, setProject }) {
  const dialog = useDialog();
  const id = project.id;
  const active = project.status === "generating";
  const [preview, setPreview] = useState(null);
  const [settings, setSettings] = useState(null);

  useEffect(() => {
    api.settings().then(setSettings).catch(() => {});
  }, []);

  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => api.project(id).then(setProject).catch(() => {}), 3000);
    return () => clearInterval(t);
  }, [id, active, setProject]);

  const done = project.scenes.filter((s) => s.image_status === "done").length;
  const failed = project.scenes.filter((s) => s.image_status === "failed").length;
  const pct = Math.round((done / project.scenes.length) * 100);
  const vertical = project.format === "9:16";
  const act = (fn) => () => fn().then(setProject).catch((e) => dialog.alert({ title: "Aksi gagal", message: e.message }));
  const [narrationIndex, setNarrationIndex] = useState(null);
  const [cols, setCols] = useGridCols(project.format);
  const compact = cols === 4; // narrow cards: icon-only actions, shorter narration

  const failedNav = useFailedNav(
    project.scenes.flatMap((s, i) => (s.image_status === "failed" ? [i] : [])),
    "scene-"
  );
  const flash = failedNav.flash;

  // Estimasi durasi selesai
  const remainingScenes = project.scenes.filter((s) => s.image_status !== "done" && !s.is_merged).length;
  const avgDelay = settings?.delay_between_images ? (settings.delay_between_images.min + settings.delay_between_images.max) / 2 : 10;
  const avgFlowRender = 16;
  const concurrency = (settings?.concurrent_generate ?? true) ? (settings?.max_concurrency ?? 3) : 1;
  const timePerImage = avgFlowRender + avgDelay;
  const totalSecondsRemaining = Math.round((remainingScenes * timePerImage) / Math.max(1, concurrency));
  const etaMinutes = Math.floor(totalSecondsRemaining / 60);
  const etaSeconds = totalSecondsRemaining % 60;
  const etaText = etaMinutes > 0 ? `±${etaMinutes} mnt ${etaSeconds > 0 ? `${etaSeconds} dtk` : ""}` : `±${etaSeconds} dtk`;

  async function retry(i) {
    const failed = project.scenes[i].image_status === "failed";
    const ok = await dialog.confirm({
      title: failed ? `Coba generate frame ${i + 1} lagi?` : `Generate ulang frame ${i + 1}?`,
      message: failed
        ? "Frame ini akan dimasukkan kembali ke antrian worker Flow."
        : "Gambar lama akan diganti dengan yang baru dari Flow. Pastikan tab Flow terbuka dan worker dalam status ON.",
      confirmLabel: failed ? "Ya, Coba Lagi" : "Ya, Generate Ulang",
    });
    if (ok) act(() => api.retry(id, i))();
  }
  const redownload = (i) => act(() => api.redownload(id, i))();
  const lowRes = project.scenes.filter((s) => s.needs_hd).length;

  async function handleClearImages() {
    const ok = await dialog.confirm({
      title: "Bersihkan Semua Gambar?",
      message: "Semua file gambar yang sudah ter-generate pada project ini akan dihapus dari folder output dan semua frame kembali ke status awal (pending / fresh). Naskah cerita dan kode prompt tetap utuh.",
      confirmLabel: "Bersihkan Semua Gambar",
      danger: true,
    });
    if (!ok) return;
    try {
      const updated = await api.clearImages(id);
      setProject(updated);
    } catch (e) {
      await dialog.alert({ title: "Gagal membersihkan gambar", message: e.message });
    }
  }

  async function handleTestRun(count = 2) {
    try {
      const updated = await api.testRun(id, count);
      setProject(updated);
    } catch (e) {
      await dialog.alert({ title: "Gagal memulai test run", message: e.message });
    }
  }

  async function handleSwap(a, b) {
    try {
      const updated = await api.swapScenes(id, a, b);
      setProject(updated);
    } catch (e) {
      await dialog.alert({ title: "Gagal menukar posisi gambar", message: e.message });
    }
  }

  return (
    <div className="space-y-6">
      {/* Telemetry & Studio Dock */}
      <div className="panel p-6 space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold tracking-tight text-slate-100">{project.title}</h1>
            {project.core_answer && (
              <p className="mt-1 text-sm text-slate-300 leading-relaxed max-w-3xl">{project.core_answer}</p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <span className="rounded-md border border-[#292e3b] bg-[#1e222b] px-2.5 py-1 font-mono text-xs text-slate-300">
              {project.format}
            </span>
            <span className={`rounded-md border px-2.5 py-1 font-mono text-xs ${BADGE[project.status] ?? "border-slate-700 bg-slate-800 text-slate-300"}`}>
              {project.status.toUpperCase()}
            </span>
          </div>
        </div>

        {/* Progress Bar with Monospace Indicators & ETA */}
        <div className="space-y-1.5">
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs font-mono text-slate-400">
            <span>
              Progres Produksi: <b className="text-amber-400 font-semibold">{done}</b> / {project.scenes.length} frame selesai
              {failed > 0 && (
                <button
                  className="ml-2 text-red-400 underline decoration-dotted underline-offset-2 hover:text-red-300"
                  onClick={() => failedNav.goTo(1)}
                  title="Lompat ke frame yang gagal"
                >
                  ({failed} gagal)
                </button>
              )}
            </span>
            <div className="flex items-center gap-3">
              {project.status === "generating" && remainingScenes > 0 && (
                <span className="flex items-center gap-1.5 rounded-md border border-amber-500/30 bg-amber-500/10 px-2.5 py-0.5 font-mono text-xs font-semibold text-amber-300 shadow-2xs">
                  <Clock size={12} className="text-amber-400" />
                  <span>Sisa Waktu: <b>{etaText}</b></span>
                  <span className="text-amber-400/70 font-normal">({remainingScenes} frame · {concurrency} slot)</span>
                </span>
              )}
              {project.status === "done" && (
                <span className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-0.5 font-mono text-xs font-semibold text-emerald-300">
                  Semua Selesai ✓
                </span>
              )}
              <span className="font-semibold text-slate-200">{pct}%</span>
            </div>
          </div>
          <div className="h-2.5 overflow-hidden rounded-full border border-[#292e3b] bg-[#12141a]">
            <div
              className="h-full bg-amber-500 transition-all duration-300 shadow-sm"
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>

        {/* Controls Bar */}
        <div className="flex flex-wrap items-center gap-2.5 pt-1">
          {project.status === "generating" && (
            <button className="btn-ghost text-xs" onClick={act(() => api.pause(id))}>
              <Pause size={14} className="text-amber-400" /> Jeda Worker
            </button>
          )}
          {project.status === "paused" && (
            <button className="btn-primary text-xs" onClick={act(() => api.resume(id))}>
              <Play size={14} /> Lanjutkan Worker
            </button>
          )}
          <button
            className="btn-ghost text-xs border-amber-500/40 text-amber-300 hover:bg-amber-500/10"
            onClick={() => handleTestRun(2)}
            title="Generate hanya 2 frame untuk testing, lalu otomatis jeda"
          >
            <Zap size={14} className="text-amber-400" /> Test (2 Frame)
          </button>
          {lowRes > 0 && (
            <button className="btn-primary text-xs" onClick={act(() => api.redownloadAll(id))}>
              <Download size={14} /> Ambil 2K Semua ({lowRes})
            </button>
          )}
          <button
            className="btn-ghost text-xs text-rose-400 hover:text-rose-300 hover:border-rose-500/40"
            onClick={handleClearImages}
            title="Hapus semua gambar yang sudah digenerate agar antrean kembali fresh dari frame #1"
          >
            <Trash2 size={14} /> Bersihkan Gambar (Fresh)
          </button>
          <a className="btn-ghost ml-auto text-xs" href={api.downloadUrl(id)}>
            <FileArchive size={14} className="text-amber-400" /> Unduh Paket ZIP
          </a>
        </div>

        {/* Informational Callouts */}
        {lowRes > 0 && (
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3.5 text-xs leading-relaxed text-amber-200 flex items-start gap-2.5">
            <AlertTriangle size={15} className="text-amber-400 shrink-0 mt-0.5" />
            <div>
              <b>{lowRes} gambar</b> masih beresolusi thumbnail rendah. Klik "Ambil 2K Semua" untuk mengunduh versi resolusi tinggi dari Flow tanpa kuota generate ulang. Pastikan tab Flow aktif.
            </div>
          </div>
        )}

        {active && (
          <div className="rounded-xl border border-[#292e3b] bg-[#12141a] p-3.5 text-xs text-slate-300 flex items-center gap-2.5">
            <Zap size={15} className="text-amber-400 shrink-0 animate-pulse" />
            <div>
              Worker sedang aktif. Pastikan tab Google Flow tetap terbuka dan status worker di Chrome Extension adalah <b className="text-amber-300">ON</b>.
            </div>
          </div>
        )}
      </div>

      {/* Frame Reel Grid */}
      <div className="flex items-center justify-between gap-3">
        <span className="font-mono text-xs text-slate-400">{project.scenes.length} frame</span>
        <div className="flex items-center gap-1 rounded-lg border border-[#292e3b] bg-[#12141a] p-1" role="group" aria-label="Jumlah kolom">
          {[2, 3, 4].map((n) => {
            const Icon = GRID_ICON[n];
            return (
              <button
                key={n}
                onClick={() => setCols(n)}
                aria-pressed={cols === n}
                title={`${n} kolom`}
                className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs transition ${
                  cols === n ? "bg-amber-500/15 text-amber-300" : "text-slate-400 hover:bg-[#1e222b] hover:text-slate-200"
                }`}
              >
                <Icon size={14} /> {n}
              </button>
            );
          })}
        </div>
      </div>

      <div className={`grid items-start ${compact ? "gap-3" : "gap-4"} ${vertical ? "grid-cols-2" : "grid-cols-1"} ${GRID_COLS[cols]}`}>
        {project.scenes.map((s, i) => (
          <div
            key={i}
            id={`scene-${i}`}
            className={`card overflow-hidden transition-all hover:border-[#3d4455] flex flex-col scroll-mt-24 ${
              flash === i ? "ring-2 ring-red-400 ring-offset-2 ring-offset-[#0f1117]" : s.image_status === "failed" ? "border-red-500/40" : ""
            }`}
          >
            <button
              className={`${vertical ? "aspect-[9/16]" : "aspect-video"} group relative flex w-full items-center justify-center overflow-hidden bg-[#12141a] border-b border-[#292e3b]`}
              onClick={() => setPreview(i)}
            >
              {s.image_file ? (
                <>
                  <img
                    src={api.fileUrl(id, s.image_file, project.updated_at)}
                    alt={`Scene ${i + 1}`}
                    className="h-full w-full object-cover transition duration-200 group-hover:scale-[1.02]"
                  />
                  <span className="absolute inset-0 flex items-center justify-center bg-black/50 text-xs font-semibold text-white opacity-0 transition duration-150 group-hover:opacity-100">
                    <Maximize2 size={15} className="mr-1.5 text-amber-400" /> Pratinjau Frame
                  </span>
                  <a
                    href={api.fileUrl(id, s.image_file, project.updated_at)}
                    download={`scene_${String(i + 1).padStart(3, "0")}.${s.image_file.split(".").pop()}`}
                    onClick={(e) => e.stopPropagation()}
                    className="absolute top-2 right-2 z-10 rounded-lg bg-black/70 p-1.5 text-slate-200 backdrop-blur hover:bg-black hover:text-amber-400 transition"
                    title={`Unduh Scene #${i + 1}`}
                  >
                    <Download size={14} />
                  </a>
                </>
              ) : (
                <div className="flex flex-col items-center gap-2 p-4 text-center">
                  <span className="font-mono text-xs font-semibold text-slate-400">FRAME #{i + 1}</span>
                  <span className={`rounded border px-2 py-0.5 font-mono text-[11px] ${BADGE[s.image_status]}`}>
                    {s.is_merged ? "DUAL MERGED" : s.image_status}
                  </span>
                </div>
              )}
            </button>

            <div className={`flex flex-col flex-1 justify-between ${compact ? "p-2.5 space-y-2" : "p-3.5 space-y-2.5"}`}>
              <div className="space-y-1.5">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-xs font-bold text-slate-300">
                    #{i + 1}
                    {s.tag && <span className="ml-1 text-[10px] text-slate-400 font-mono">· {s.tag}</span>}
                    {s.title_text && <span className="ml-2 font-sans font-semibold text-amber-300">{s.title_text}</span>}
                  </span>
                  <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-mono ${BADGE[s.image_status]}`}>
                    {s.is_merged
                      ? `DUAL (Scene ${(s.merged_with ?? i - 1) + 1})`
                      : s.job_kind === "redownload" && s.image_status !== "done"
                      ? `2K ${s.image_status}`
                      : s.image_status === "done"
                      ? s.image_res === "thumbnail"
                        ? "THUMBNAIL"
                        : s.image_res ?? "done"
                      : s.image_status}
                  </span>
                </div>

                {s.is_merged && (
                  <div className="text-[11px] text-amber-300/90 font-mono">
                    Gambar sama dengan Scene {(s.merged_with ?? i - 1) + 1}
                  </div>
                )}

                <p className={`text-xs leading-relaxed text-slate-300 ${compact ? "line-clamp-2" : "line-clamp-3"}`}>{s.narration}</p>
                <SceneNote scene={s} />
              </div>

              <div className="pt-2 border-t border-[#292e3b]/60 space-y-1.5">
                <div className="flex gap-1.5">
                  <button
                    className="btn-ghost flex-1 py-1.5 text-[11px]"
                    onClick={() => setNarrationIndex(i)}
                    title="Ubah teks narasi"
                  >
                    <WandSparkles size={12} className="text-amber-400" /> {!compact && "Narasi"}
                  </button>
                  {(s.image_status === "failed" || s.image_status === "done") && !s.is_merged && (
                    <button
                      className="btn-ghost flex-1 py-1.5 text-[11px]"
                      onClick={() => retry(i)}
                      title="Generate ulang di Flow"
                    >
                      <RotateCcw size={12} /> {!compact && (s.image_status === "failed" ? "Coba Lagi" : "Ulang")}
                    </button>
                  )}
                  {s.image_file && (
                    <a
                      className="btn-ghost py-1.5 px-2.5 text-[11px] text-emerald-400 hover:text-emerald-300 flex items-center gap-1"
                      href={api.fileUrl(id, s.image_file, project.updated_at)}
                      download={`scene_${String(i + 1).padStart(3, "0")}.${s.image_file.split(".").pop()}`}
                      title={`Unduh file frame #${i + 1}`}
                    >
                      <Download size={12} /> {!compact && "Unduh"}
                    </a>
                  )}
                  {s.image_file && i < project.scenes.length - 1 && (
                    <button
                      className="btn-ghost py-1.5 px-2 text-[11px] text-amber-300 hover:text-amber-200"
                      onClick={() => handleSwap(i, i + 1)}
                      title={`Tukar gambar dengan Frame #${i + 2}`}
                    >
                      <ArrowRightLeft size={12} /> {compact ? `#${i + 2}` : `Tukar #${i + 2}`}
                    </button>
                  )}
                </div>
                {s.needs_hd && (
                  <button className="btn-primary w-full py-1 text-[11px]" onClick={() => redownload(i)}>
                    <Download size={12} /> Ambil 2K
                  </button>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      <FailedNav nav={failedNav} />

      {preview !== null && (
        <Lightbox
          project={project}
          index={preview}
          onClose={() => setPreview(null)}
          onNavigate={setPreview}
          onRetry={retry}
          onRedownload={redownload}
          onEditNarration={(i) => {
            setPreview(null);
            setNarrationIndex(i);
          }}
        />
      )}

      <NarrationEditor
        open={narrationIndex !== null}
        onClose={() => setNarrationIndex(null)}
        projectId={id}
        index={narrationIndex ?? 0}
        current={project.scenes[narrationIndex ?? 0]?.narration ?? ""}
        onApply={async (text) => setProject(await api.setNarration(id, narrationIndex, text))}
      />
    </div>
  );
}
