import { AlertCircle, AudioLines, CheckCircle2, Clapperboard, Download, ExternalLink, FileArchive, Image as ImageIcon, Music, Sparkles } from "lucide-react";
import { useState } from "react";
import { api } from "./api.js";
import { go } from "./App.jsx";

const fmtSec = (s) => `${s.toFixed(1).replace(".", ",")} dtk`;

export default function ExportView({ project }) {
  const [filter, setFilter] = useState("all"); // 'all' | 'ready' | 'missing'
  const id = project.id;
  const scenes = project.scenes;
  const total = scenes.length;

  const imagesDone = scenes.filter((s) => s.image_status === "done").length;
  const audioDone = scenes.filter((s) => s.audio_status === "done" && !s.audio_stale).length;
  const readyDone = scenes.filter((s) => s.image_status === "done" && s.audio_status === "done" && !s.audio_stale).length;
  const staleCount = scenes.filter((s) => s.audio_stale).length;

  const totalAudioSec = scenes.reduce((sum, s) => sum + (s.audio_status === "done" ? s.audio_duration ?? 0 : 0), 0);
  const totalMin = Math.floor(totalAudioSec / 60);
  const totalRemSec = Math.round(totalAudioSec % 60);

  const filteredScenes = scenes
    .map((s, index) => ({ s, index }))
    .filter(({ s }) => {
      const isReady = s.image_status === "done" && s.audio_status === "done" && !s.audio_stale;
      if (filter === "ready") return isReady;
      if (filter === "missing") return !isReady;
      return true;
    });

  return (
    <div className="space-y-6">
      {/* Header & Export Status Panel */}
      <div className="panel space-y-5 p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold tracking-tight text-slate-100 flex items-center gap-2">
              <Clapperboard className="text-amber-400" size={22} />
              Review & Ekspor Video
            </h1>
            <p className="mt-1 text-sm text-slate-400">
              Langkah 3: Tinjau keselarasan visual gambar dan klip audio narasi per adegan sebelum dirakit ke CapCut atau video editor.
            </p>
          </div>
          <div className="flex flex-wrap gap-2.5">
            <a
              href={api.downloadUrl(id)}
              className="btn-primary text-xs flex items-center gap-2 px-4 py-2"
              download
            >
              <FileArchive size={15} /> Unduh ZIP Lengkap ({total} Adegan)
            </a>
          </div>
        </div>

        {/* Bento Stats */}
        <div className="grid gap-3 sm:grid-cols-4">
          <div className="rounded-xl border border-[#292e3b] bg-[#12141a] p-3.5 space-y-1">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <span className="flex items-center gap-1.5"><ImageIcon size={13} className="text-sky-400" /> Gambar Selesai</span>
              <span className="font-mono text-slate-300">{Math.round((imagesDone / total) * 100)}%</span>
            </div>
            <div className="text-xl font-bold font-mono text-slate-100">
              {imagesDone} <span className="text-xs text-slate-500 font-normal">/ {total}</span>
            </div>
          </div>

          <div className="rounded-xl border border-[#292e3b] bg-[#12141a] p-3.5 space-y-1">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <span className="flex items-center gap-1.5"><AudioLines size={13} className="text-emerald-400" /> Audio Narasi</span>
              <span className="font-mono text-slate-300">{Math.round((audioDone / total) * 100)}%</span>
            </div>
            <div className="text-xl font-bold font-mono text-slate-100">
              {audioDone} <span className="text-xs text-slate-500 font-normal">/ {total}</span>
            </div>
          </div>

          <div className="rounded-xl border border-[#292e3b] bg-[#12141a] p-3.5 space-y-1">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <span className="flex items-center gap-1.5"><Music size={13} className="text-amber-400" /> Total Durasi</span>
              <span className="font-mono text-slate-300">Audio</span>
            </div>
            <div className="text-xl font-bold font-mono text-amber-300">
              {totalMin}m {totalRemSec}d
            </div>
          </div>

          <div className="rounded-xl border border-[#292e3b] bg-[#12141a] p-3.5 space-y-1">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <span className="flex items-center gap-1.5"><CheckCircle2 size={13} className="text-amber-400" /> Siap Rakit</span>
              <span className="font-mono text-slate-300">{Math.round((readyDone / total) * 100)}%</span>
            </div>
            <div className="text-xl font-bold font-mono text-amber-400">
              {readyDone} <span className="text-xs text-slate-500 font-normal">/ {total}</span>
            </div>
          </div>
        </div>

        {/* Info Box */}
        <div className="rounded-xl border border-[#292e3b] bg-[#161920]/60 p-4 text-xs text-slate-300 space-y-2">
          <div className="flex items-center gap-2 font-semibold text-amber-300">
            <Sparkles size={14} /> Isi File Paket ZIP Ekspor:
          </div>
          <ul className="grid gap-1.5 sm:grid-cols-2 text-slate-400">
            <li>• File gambar urut: <code className="text-slate-300">scene_001.png</code>, <code className="text-slate-300">scene_002.png</code> ...</li>
            <li>• File audio narasi urut: <code className="text-slate-300">audio/scene_001.wav</code> ...</li>
            <li>• Transkrip naskah lengkap: <code className="text-slate-300">narration.txt</code></li>
            <li>• Metadata adegan & durasi: <code className="text-slate-300">project.json</code></li>
          </ul>
        </div>

        {/* Filter Bar */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[#292e3b] pt-4">
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400">Tampilkan:</span>
            <div className="flex rounded-lg border border-[#292e3b] bg-[#12141a] p-0.5 text-xs">
              <button
                className={`rounded px-2.5 py-1 ${filter === "all" ? "bg-amber-500/20 text-amber-300 font-semibold" : "text-slate-400 hover:text-slate-200"}`}
                onClick={() => setFilter("all")}
              >
                Semua ({total})
              </button>
              <button
                className={`rounded px-2.5 py-1 ${filter === "ready" ? "bg-emerald-500/20 text-emerald-300 font-semibold" : "text-slate-400 hover:text-slate-200"}`}
                onClick={() => setFilter("ready")}
              >
                Siap Rakit ({readyDone})
              </button>
              <button
                className={`rounded px-2.5 py-1 ${filter === "missing" ? "bg-red-500/20 text-red-300 font-semibold" : "text-slate-400 hover:text-slate-200"}`}
                onClick={() => setFilter("missing")}
              >
                Belum Lengkap ({total - readyDone})
              </button>
            </div>
          </div>

          {staleCount > 0 && (
            <span className="font-mono text-xs text-amber-300 flex items-center gap-1.5">
              <AlertCircle size={14} /> Ada {staleCount} audio basi yang perlu di-generate ulang di tab Audio
            </span>
          )}
        </div>
      </div>

      {/* Timeline Scenes Review List */}
      <div className="space-y-3">
        <h2 className="text-sm font-bold uppercase tracking-wider text-slate-400">
          Urutan Timeline Video ({filteredScenes.length} Adegan)
        </h2>

        <ul className="space-y-2.5">
          {filteredScenes.map(({ s, index: i }) => {
            const hasImg = s.image_status === "done" && s.image_file;
            const hasAudio = s.audio_status === "done" && s.audio_file && !s.audio_stale;
            const isReady = hasImg && hasAudio;

            return (
              <li
                key={i}
                className={`card flex flex-col gap-3 p-3.5 sm:flex-row sm:items-center ${
                  isReady ? "border-emerald-500/30" : "border-slate-800"
                }`}
              >
                {/* Visual Thumbnail */}
                <div className="flex items-start gap-3 sm:w-[45%]">
                  <div
                    className={`${
                      project.format === "9:16" ? "aspect-[9/16] w-14" : "aspect-video w-28"
                    } relative shrink-0 overflow-hidden rounded-md bg-[#12141a] border border-[#292e3b]`}
                  >
                    {hasImg ? (
                      <img
                        src={api.fileUrl(id, s.image_file, project.updated_at)}
                        alt={`Scene ${i + 1}`}
                        className="h-full w-full object-cover"
                        loading="lazy"
                      />
                    ) : (
                      <div className="flex h-full w-full flex-col items-center justify-center text-[10px] text-slate-500">
                        <ImageIcon size={18} className="opacity-40" />
                        <span>Belum ada</span>
                      </div>
                    )}
                  </div>
                  <div className="min-w-0 flex-1 space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs font-bold text-amber-400">#{i + 1}</span>
                      {isReady ? (
                        <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 font-mono text-[10px] text-emerald-300 border border-emerald-500/30">
                          Siap Video
                        </span>
                      ) : !hasImg && !hasAudio ? (
                        <span className="rounded bg-red-500/15 px-1.5 py-0.5 font-mono text-[10px] text-red-300 border border-red-500/30">
                          Belum Ada Aset
                        </span>
                      ) : !hasImg ? (
                        <span className="rounded bg-sky-500/15 px-1.5 py-0.5 font-mono text-[10px] text-sky-300 border border-sky-500/30">
                          Kurang Gambar
                        </span>
                      ) : (
                        <span className="rounded bg-amber-500/15 px-1.5 py-0.5 font-mono text-[10px] text-amber-300 border border-amber-500/30">
                          {s.audio_stale ? "Audio Basi" : "Kurang Audio"}
                        </span>
                      )}
                    </div>
                    <p className="text-xs leading-relaxed text-slate-200 line-clamp-3">
                      {s.narration || <i className="text-slate-500">(narasi kosong)</i>}
                    </p>
                  </div>
                </div>

                {/* Audio Player & Duration Timing */}
                <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2.5 sm:border-l sm:border-[#292e3b] sm:pl-3">
                  {hasAudio ? (
                    <div className="flex flex-1 items-center gap-2 min-w-[200px]">
                      <audio
                        controls
                        preload="none"
                        src={api.audioUrl(id, s.audio_file, s.audio_key)}
                        className="h-8 flex-1"
                      />
                      <span className="font-mono text-xs font-semibold text-amber-300 shrink-0">
                        {fmtSec(s.audio_duration ?? 0)}
                      </span>
                    </div>
                  ) : (
                    <div className="flex-1 text-xs text-slate-500 italic">
                      Audio klip narasi belum tersedia
                    </div>
                  )}

                  {/* Actions per scene */}
                  <div className="flex items-center gap-1.5 shrink-0 ml-auto">
                    {!hasImg && (
                      <button
                        className="btn-ghost px-2 py-1 text-[11px] text-sky-300 hover:text-sky-200"
                        onClick={() => go(`/project/${id}/images`)}
                      >
                        Ke Gambar
                      </button>
                    )}
                    {!hasAudio && (
                      <button
                        className="btn-ghost px-2 py-1 text-[11px] text-emerald-300 hover:text-emerald-200"
                        onClick={() => go(`/project/${id}/audio`)}
                      >
                        Ke Audio
                      </button>
                    )}
                    {hasImg && (
                      <a
                        href={api.fileUrl(id, s.image_file, project.updated_at)}
                        download
                        className="btn-ghost p-1.5 text-slate-400 hover:text-slate-200"
                        title="Unduh file gambar adegan ini"
                      >
                        <Download size={13} />
                      </a>
                    )}
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
