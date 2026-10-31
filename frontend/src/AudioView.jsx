import {
  AlertTriangle,
  AudioLines,
  Check,
  CheckCircle2,
  ChevronUp,
  Library,
  Loader2,
  Pause,
  Pencil,
  Play,
  RotateCcw,
  ShieldCheck,
  SkipBack,
  SkipForward,
  Square,
  Volume2,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import FailedNav, { useFailedNav } from "./FailedNav.jsx";
import VoiceLibrary from "./VoiceLibrary.jsx";
import { Select, useDialog } from "./ui.jsx";

const MODEL_LABEL = { omnivoice: "OmniVoice", voxcpm2: "VoxCPM2" };

const STATUS = {
  pending: ["BELUM ADA", "bg-amber-500/10 text-amber-400 border-amber-500/30"],
  queued: ["ANTRE", "bg-sky-500/15 text-sky-300 border-sky-500/35 font-semibold"],
  generating: ["MEMPROSES", "bg-amber-500/25 text-amber-200 border-amber-500/50 animate-pulse font-semibold"],
  done: ["SELESAI", "bg-emerald-500/15 text-emerald-400 border-emerald-500/35 font-semibold"],
  failed: ["GAGAL", "bg-red-500/20 text-red-300 border-red-500/40 font-semibold"],
  stale: ["PERLU UPDATE", "bg-orange-500/15 text-orange-300 border-orange-500/30 font-semibold"],
};

const fmtSec = (s) => `${s.toFixed(1).replace(".", ",")} dtk`;

const fmtTime = (s) => {
  if (!s || isNaN(s)) return "0:00";
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
};

function WorkerBadges({ status }) {
  const online = (status?.workers ?? []).filter((w) => w.online);
  if (!online.length) {
    return <span className="rounded-md border border-[#292e3b] bg-[#12141a] px-2 py-1 font-mono text-[11px] text-slate-400">Worker offline</span>;
  }
  return online.map((w) => (
    <span key={w.name} className="flex items-center gap-1.5 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-2 py-1 font-mono text-[11px] text-emerald-300" title={`Model: ${w.models.join(", ")}`}>
      <span className="size-1.5 rounded-full bg-emerald-400" />
      {w.name} · {w.device || "?"}
    </span>
  ));
}

function NarrationText({ scene, onSave }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(scene.narration);
  const [saving, setSaving] = useState(false);

  if (!editing) {
    return (
      <button className="group flex w-full items-start gap-1.5 text-left text-sm leading-relaxed text-slate-200" onClick={() => (setText(scene.narration), setEditing(true))} title="Ubah narasi">
        <span className="min-w-0 flex-1">{scene.narration || <i className="text-slate-500">(narasi kosong)</i>}</span>
        <Pencil size={12} className="mt-1 shrink-0 text-slate-500 opacity-0 group-hover:opacity-100" />
      </button>
    );
  }
  return (
    <div className="space-y-1.5">
      <textarea className="input min-h-16 resize-y text-sm" value={text} onChange={(e) => setText(e.target.value)} autoFocus />
      <div className="flex gap-1.5">
        <button
          className="btn-primary px-2.5 py-1 text-[11px]"
          disabled={saving || !text.trim()}
          onClick={async () => {
            setSaving(true);
            try {
              await onSave(text.trim());
              setEditing(false);
            } finally {
              setSaving(false);
            }
          }}
        >
          <Check size={12} /> Simpan
        </button>
        <button className="btn-ghost px-2.5 py-1 text-[11px]" onClick={() => setEditing(false)}>
          <X size={12} /> Batal
        </button>
      </div>
    </div>
  );
}

function AuditModal({ data, onClose, onRegenerate }) {
  if (!data) return null;
  const { scene, index, isGrouped, groupScenes } = data;
  const score = Math.round((scene.audio_audit_score ?? 0) * 100);
  const isWarning = scene.audio_audit_status === "warning";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-xs animate-in fade-in duration-150">
      <div className="relative w-full max-w-lg rounded-xl border border-slate-700/80 bg-[#161922] p-5 shadow-2xl space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2">
            <span className="font-mono text-sm font-bold text-slate-300">Scene #{index + 1}</span>
            {isWarning ? (
              <span className="rounded-md border border-amber-500/50 bg-amber-500/15 px-2 py-0.5 font-mono text-xs text-amber-300 font-bold flex items-center gap-1.5">
                <AlertTriangle size={13} className="text-amber-400" />
                <span>Peringatan Pelafalan ({score}%)</span>
              </span>
            ) : (
              <span className="rounded-md border border-emerald-500/40 bg-emerald-500/15 px-2 py-0.5 font-mono text-xs text-emerald-400 font-bold flex items-center gap-1.5">
                <CheckCircle2 size={13} />
                <span>Pelafalan Akurat ({score}%)</span>
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="rounded-md p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white transition"
            title="Tutup"
          >
            <X size={18} />
          </button>
        </div>

        {/* Content Comparison */}
        <div className="space-y-3">
          {/* Target Script */}
          <div className="rounded-lg border border-slate-800 bg-[#1c202c] p-3">
            <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400 mb-1 font-semibold">
              Naskah Asli (Target Script):
            </div>
            <div className="text-sm font-medium text-slate-100 leading-relaxed">
              {scene.narration}
            </div>
          </div>

          {/* Whisper Heard */}
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3">
            <div className="text-[10px] font-mono uppercase tracking-wider text-amber-400 mb-1 font-semibold flex items-center gap-1">
              <Volume2 size={12} />
              <span>Yang Didengar & Ditranskripsikan Whisper:</span>
            </div>
            <div className="text-sm font-mono text-amber-200 leading-relaxed">
              "{scene.audio_audit_text || "(Belum ada data transkripsi)"}"
            </div>
          </div>

          {/* Detected Issues */}
          {scene.audio_audit_issues?.length > 0 && (
            <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 space-y-1.5">
              <div className="text-[10px] font-mono uppercase tracking-wider text-red-400 font-bold">
                Masalah Pelafalan Terdeteksi:
              </div>
              <ul className="list-disc list-inside text-xs text-red-300 space-y-1">
                {scene.audio_audit_issues.map((iss, idx) => (
                  <li key={idx}>{iss}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="text-[11px] text-slate-400 leading-normal bg-slate-800/40 p-2.5 rounded border border-slate-800/70">
            💡 <span className="font-semibold text-slate-300">Kenapa ini terjadi?</span> Model suara TTS terkadang berbicara terlalu cepat, menyatukan dua kata, atau menelan suku kata di akhir kata. Jika suara di scene ini terdengar janggal, klik tombol <b className="text-emerald-400">Generate Ulang</b> di bawah untuk mengambil take suara baru.
          </div>
        </div>

        {/* Footer Actions */}
        <div className="flex items-center justify-end gap-2 border-t border-slate-800 pt-3">
          <button
            onClick={onClose}
            className="rounded-lg border border-slate-700 bg-slate-800/60 px-4 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-700 hover:text-white transition"
          >
            Tutup
          </button>
          <button
            onClick={() => {
              onClose();
              onRegenerate(data);
            }}
            className="rounded-lg bg-emerald-600 hover:bg-emerald-500 px-4 py-2 text-xs font-bold text-white flex items-center gap-1.5 shadow-md shadow-emerald-950/40 transition"
          >
            <RotateCcw size={13} />
            <span>{isGrouped ? `Generate Ulang Grup #${(scene.sentence_group ?? 0) + 1}` : "Generate Ulang Scene Ini"}</span>
          </button>
        </div>
      </div>
    </div>
  );
}

// Step 2: one narration clip per scene, generated by the TTS worker.
export default function AudioView({ project, setProject }) {
  const dialog = useDialog();
  const id = project.id;
  const [voices, setVoices] = useState([]);
  const [settings, setSettings] = useState(null);
  const [status, setStatus] = useState(null);
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [playingPreview, setPlayingPreview] = useState(false);
  const previewAudioRef = useRef(null);

  // Audit Inspection Modal State
  const [auditModalScene, setAuditModalScene] = useState(null);

  // Play All Sequential Playback State
  const [playingAll, setPlayingAll] = useState(false);
  const [currentPlayingIndex, setCurrentPlayingIndex] = useState(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playCurrentTime, setPlayCurrentTime] = useState(0);
  const [playDuration, setPlayDuration] = useState(0);
  const playAllAudioRef = useRef(null);
  const stopRequestedRef = useRef(false);

  // Floating Scroll-To-Top State
  const [showScrollTop, setShowScrollTop] = useState(false);
  const [auditing, setAuditing] = useState(false);

  const runAudit = async () => {
    setAuditing(true);
    try {
      const updated = await api.auditAudio(id);
      setProject(updated);
      dialog.alert({
        title: "Audit Pelafalan Selesai",
        message: "Pemeriksaan konsistensi audio telah selesai. Scene yang memiliki catatan pelafalan ditandai dengan badge kuning 'Cek Pelafalan'.",
      });
    } catch (err) {
      dialog.alert({
        title: "Gagal Audit",
        message: String(err?.message || err),
      });
    } finally {
      setAuditing(false);
    }
  };

  useEffect(() => {
    const onScroll = () => {
      setShowScrollTop(window.scrollY > 220);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const scrollToTop = () => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  function stopPreview() {
    if (previewAudioRef.current) {
      previewAudioRef.current.pause();
      previewAudioRef.current = null;
    }
    setPlayingPreview(false);
  }

  function togglePreview(voiceId) {
    if (previewAudioRef.current) {
      previewAudioRef.current.pause();
      previewAudioRef.current = null;
    }
    if (playingPreview) {
      setPlayingPreview(false);
      return;
    }
    if (!voiceId) return;
    if (playingAll) stopPlayAll();
    const a = new Audio(api.voiceAudioUrl(voiceId));
    previewAudioRef.current = a;
    setPlayingPreview(true);
    a.play().catch(() => {
      setPlayingPreview(false);
      previewAudioRef.current = null;
    });
    a.onended = () => {
      setPlayingPreview(false);
      previewAudioRef.current = null;
    };
    a.onerror = () => {
      setPlayingPreview(false);
      previewAudioRef.current = null;
    };
  }

  useEffect(() => {
    return () => {
      stopPreview();
      if (playAllAudioRef.current) {
        playAllAudioRef.current.pause();
        playAllAudioRef.current = null;
      }
    };
  }, []);

  const scenes = project.scenes;
  const busy = scenes.some((s) => s.audio_status === "queued" || s.audio_status === "generating");
  const done = scenes.filter((s) => s.audio_status === "done" && !s.audio_stale).length;
  const stale = scenes.filter((s) => s.audio_stale).length;
  const queued = scenes.filter((s) => s.audio_status === "queued").length;
  const generating = scenes.filter((s) => s.audio_status === "generating").length;
  const totalSec = scenes.reduce((sum, s) => sum + (s.audio_status === "done" ? s.audio_duration ?? 0 : 0), 0);
  const failedNav = useFailedNav(
    scenes.flatMap((s, i) => (s.audio_status === "failed" ? [i] : [])),
    "audio-scene-"
  );

  useEffect(() => {
    api.voices().then(setVoices).catch(() => {});
    api.settings().then(setSettings).catch(() => {});
  }, []);

  // fast refresh while the worker has work, slow refresh otherwise (worker badge)
  useEffect(() => {
    const tick = () => {
      api.ttsStatus().then(setStatus).catch(() => {});
      if (busy) api.project(id).then(setProject).catch(() => {});
    };
    tick();
    const t = setInterval(tick, busy ? 3000 : 15000);
    return () => clearInterval(t);
  }, [id, busy, setProject]);

  const act = async (fn) => {
    try {
      setProject(await fn());
    } catch (e) {
      await dialog.alert({ title: "Aksi gagal", message: e.message });
    }
  };

  const defaultVoice = voices.find((v) => v.id === settings?.tts_voice_id);
  const voiceOptions = [
    { value: "", label: `Default${defaultVoice ? ` (${defaultVoice.name})` : " (belum diatur)"}` },
    ...voices.map((v) => ({
      value: v.id,
      label: v.name,
      desc: `${v.duration.toFixed(1)} dtk · ${(v.speed ?? (v.id === "suara-2" ? 0.9 : 1.0)).toFixed(2)}x`,
    })),
  ];
  const modelOptions = [
    { value: "", label: `Default (${MODEL_LABEL[settings?.tts_model] ?? "OmniVoice"})` },
    { value: "omnivoice", label: "OmniVoice", desc: "24 kHz · ringan, cocok untuk Mac" },
    { value: "voxcpm2", label: "VoxCPM2", desc: "48 kHz · lebih berat, paling enak di GPU NVIDIA" },
  ];
  const activeVoiceId = project.voice_id || settings?.tts_voice_id || (voices[0]?.id ?? "suara-1");
  const activeVoice = voices.find((v) => v.id === activeVoiceId);
  const currentVoiceSpeed = activeVoice?.speed ?? (activeVoiceId === "suara-2" ? 0.9 : 1.0);
  const setTts = (patch) =>
    act(() => api.setProjectTts(id, { voice_id: project.voice_id, tts_model: project.tts_model, ...patch }));

  async function regenerateAll() {
    const ok = await dialog.confirm({
      title: "Ulang semua audio?",
      message: `Semua ${scenes.length} scene akan digenerate ulang, termasuk yang sudah selesai. Bisa makan waktu lama.`,
      confirmLabel: "Ya, Ulang Semua",
    });
    if (ok) act(() => api.generateAudio(id, { mode: "all" }));
  }

  // --- PLAY ALL SEQUENTIAL PLAYBACK LOGIC ---
  const stopPlayAll = () => {
    stopRequestedRef.current = true;
    if (playAllAudioRef.current) {
      const a = playAllAudioRef.current;
      a.onended = null;
      a.onerror = null;
      a.ontimeupdate = null;
      a.pause();
      a.removeAttribute("src");
      a.load();
      playAllAudioRef.current = null;
    }
    setPlayingAll(false);
    setCurrentPlayingIndex(null);
    setIsPlaying(false);
    setPlayCurrentTime(0);
    setPlayDuration(0);
  };

  const findNextPlayable = (startIdx) => {
    for (let i = startIdx; i < scenes.length; i++) {
      if (scenes[i].audio_status === "done" && scenes[i].audio_file) {
        return i;
      }
    }
    return -1;
  };

  const findPrevPlayable = (startIdx) => {
    for (let i = startIdx - 1; i >= 0; i--) {
      if (scenes[i].audio_status === "done" && scenes[i].audio_file) {
        return i;
      }
    }
    return -1;
  };

  const playSceneAudio = (index) => {
    if (stopRequestedRef.current) return;
    if (index < 0 || index >= scenes.length) {
      stopPlayAll();
      return;
    }
    const s = scenes[index];
    if (!s.audio_file || s.audio_status !== "done") {
      const next = findNextPlayable(index + 1);
      if (next !== -1) {
        playSceneAudio(next);
      } else {
        stopPlayAll();
      }
      return;
    }

    stopPreview();

    // Detach listeners from previous audio if any
    if (playAllAudioRef.current) {
      const old = playAllAudioRef.current;
      old.onended = null;
      old.onerror = null;
      old.ontimeupdate = null;
      old.pause();
    } else {
      playAllAudioRef.current = new Audio();
    }

    const a = playAllAudioRef.current;
    const isGroupedPlay = (s.sentence_group_size ?? 1) > 1;
    const audioSrc = isGroupedPlay && s.sentence_group_audio
      ? api.audioUrl(id, s.sentence_group_audio, s.audio_key)
      : api.audioUrl(id, s.audio_file, s.audio_key);
    a.src = audioSrc;
    a.currentTime = 0;

    a.ontimeupdate = () => {
      if (stopRequestedRef.current) return;
      setPlayCurrentTime(a.currentTime);
      setPlayDuration(a.duration || (isGroupedPlay ? s.sentence_group_duration : s.audio_duration) || 0);
    };

    a.onended = () => {
      if (stopRequestedRef.current) return;
      const nextIdx = isGroupedPlay && s.sentence_group_scenes
        ? s.sentence_group_scenes[s.sentence_group_scenes.length - 1] + 1
        : index + 1;
      const next = findNextPlayable(nextIdx);
      if (next !== -1) {
        playSceneAudio(next);
      } else {
        stopPlayAll();
      }
    };

    a.onerror = () => {
      if (stopRequestedRef.current) return;
      const next = findNextPlayable(index + 1);
      if (next !== -1) {
        playSceneAudio(next);
      } else {
        stopPlayAll();
      }
    };

    setCurrentPlayingIndex(index);
    setPlayingAll(true);
    setIsPlaying(true);
    setPlayCurrentTime(0);
    setPlayDuration(s.audio_duration || 0);

    a.play().catch((err) => {
      if (!stopRequestedRef.current) {
        console.warn("Playback error:", err);
        setIsPlaying(false);
      }
    });

    // Auto-scroll to currently playing scene
    const el = document.getElementById(`audio-scene-${index}`);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  };

  const startPlayAll = (fromIndex = 0) => {
    stopRequestedRef.current = false;
    const target = findNextPlayable(fromIndex);
    if (target === -1) {
      dialog.alert({
        title: "Audio Belum Siap",
        message: "Belum ada adegan dengan audio selesai untuk diputar.",
      });
      return;
    }
    playSceneAudio(target);
  };

  const togglePlayPause = () => {
    if (!playingAll || currentPlayingIndex === null) {
      startPlayAll(0);
      return;
    }
    const a = playAllAudioRef.current;
    if (!a) return;
    if (isPlaying) {
      a.pause();
      setIsPlaying(false);
    } else {
      stopRequestedRef.current = false;
      a.play().then(() => setIsPlaying(true)).catch(() => {});
    }
  };

  const playNextScene = () => {
    stopRequestedRef.current = false;
    if (currentPlayingIndex === null) return;
    const next = findNextPlayable(currentPlayingIndex + 1);
    if (next !== -1) {
      playSceneAudio(next);
    }
  };

  const playPrevScene = () => {
    stopRequestedRef.current = false;
    if (currentPlayingIndex === null) return;
    const prev = findPrevPlayable(currentPlayingIndex);
    if (prev !== -1) {
      playSceneAudio(prev);
    }
  };

  return (
    <div className="relative">
      {/* SECTION AUDIO NARASI (Sticky container at top: 0 with solid canvas background to mask scrolling scenes) */}
      <div className="sticky top-0 z-30 bg-[#0e1015] pt-2 pb-3 -mx-2 px-2">
        <div className="panel space-y-4 p-5 sm:p-6 bg-[#161920] shadow-2xl border border-[#292e3b]">
          <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold tracking-tight text-slate-100 flex items-center gap-2">
              <span>Audio Narasi</span>
              {playingAll && isPlaying && (
                <span className="flex items-center gap-1 text-[11px] font-mono text-amber-300 font-normal bg-amber-500/15 border border-amber-500/30 px-2 py-0.5 rounded-full animate-pulse">
                  <Volume2 size={12} /> Play All Aktif
                </span>
              )}
            </h1>
            <p className="mt-1 text-sm text-slate-400">Satu klip suara per scene, dibuat oleh worker TTS di Mac atau PC.</p>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <WorkerBadges status={status} />
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-[1.2fr_0.9fr_1fr_auto]">
          <div>
            <label className="label">Suara</label>
            <div className="flex gap-1.5">
              <Select className="flex-1" value={project.voice_id ?? ""} onChange={(v) => setTts({ voice_id: v || null })} options={voiceOptions} />
              <button
                className={`btn-ghost px-2.5 transition ${playingPreview ? "text-amber-300 bg-amber-500/15" : ""}`}
                disabled={!activeVoiceId}
                onClick={() => togglePreview(activeVoiceId)}
                title={playingPreview ? "Hentikan contoh suara" : "Putar contoh suara"}
                aria-label={playingPreview ? "Hentikan contoh suara" : "Putar contoh suara"}
              >
                {playingPreview ? <Pause size={14} /> : <Play size={14} />}
              </button>
            </div>
          </div>
          <div>
            <label className="label flex items-center justify-between">
              <span>Kecepatan</span>
              <span className="font-mono text-[11px] font-semibold text-amber-400">
                {currentVoiceSpeed.toFixed(2)}x
              </span>
            </label>
            <Select
              value={String(currentVoiceSpeed.toFixed(2))}
              onChange={async (v) => {
                const spd = parseFloat(v);
                if (activeVoiceId) {
                  try {
                    await api.setVoiceSpeed(activeVoiceId, spd);
                    setVoices((prev) =>
                      prev.map((item) => (item.id === activeVoiceId ? { ...item, speed: spd } : item))
                    );
                  } catch (err) {
                    console.error("Gagal menyimpan kecepatan suara:", err);
                  }
                }
              }}
              options={[
                { value: "0.80", label: "0.80x (Sangat Santai)" },
                { value: "0.85", label: "0.85x (Pelan & Bernafas)" },
                { value: "0.90", label: "0.90x (Direkomendasikan ⭐)" },
                { value: "0.95", label: "0.95x (Sedikit Lebih Santai)" },
                { value: "1.00", label: "1.00x (Normal / Standar)" },
                { value: "1.05", label: "1.05x (Agak Cepat)" },
                { value: "1.10", label: "1.10x (Cepat)" },
                { value: "1.15", label: "1.15x (Sangat Cepat)" },
              ]}
            />
          </div>
          <div>
            <label className="label">Model</label>
            <Select value={project.tts_model ?? ""} onChange={(v) => setTts({ tts_model: v || null })} options={modelOptions} />
          </div>
          <div className="flex items-end">
            <button className="btn-ghost w-full text-xs" onClick={() => setLibraryOpen(true)}>
              <Library size={14} /> Kelola suara
            </button>
          </div>
        </div>

        {/* Action bar */}
        <div className="flex flex-wrap items-center gap-2.5 border-t border-[#292e3b] pt-4">
          <span className="font-mono text-xs text-slate-400">
            Audio <b className="text-amber-400">{done}</b>/{scenes.length}
            {stale > 0 && <span className="ml-2 text-amber-300">({stale} basi)</span>}
            {totalSec > 0 && <span className="ml-2">· total {Math.floor(totalSec / 60)}m {Math.round(totalSec % 60)}d</span>}
          </span>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            {/* Tombol Audit Pelafalan */}
            {done > 0 && (
              <button
                className="btn-ghost text-xs flex items-center gap-1.5 text-slate-300 hover:text-white border border-[#292e3b] px-2.5 py-1.5 rounded-md"
                onClick={runAudit}
                disabled={auditing}
                title="Audit konsistensi teks dan pelafalan seluruh audio menggunakan Whisper"
              >
                {auditing ? (
                  <>
                    <Loader2 size={13} className="animate-spin text-amber-400" />
                    <span>Mengaudit...</span>
                  </>
                ) : (
                  <>
                    <ShieldCheck size={14} className="text-emerald-400" />
                    <span>Audit Pelafalan</span>
                  </>
                )}
              </button>
            )}

            {/* Tombol Play All */}
            {done > 0 && (
              <button
                className={`btn text-xs flex items-center gap-1.5 font-semibold transition ${
                  playingAll
                    ? "bg-amber-500 text-slate-950 shadow-md shadow-amber-500/20 hover:bg-amber-400 active:bg-amber-600"
                    : "border border-amber-500/40 bg-amber-500/10 text-amber-300 hover:bg-amber-500/20 hover:border-amber-500/60"
                }`}
                onClick={togglePlayPause}
                title={playingAll ? (isPlaying ? "Jeda putar semua audio" : "Lanjutkan putar audio") : "Putar semua audio secara berurutan"}
              >
                {playingAll ? (
                  isPlaying ? (
                    <>
                      <Pause size={13} className="fill-current" />
                      <span>Jeda Putar ({currentPlayingIndex !== null ? `#${currentPlayingIndex + 1}` : ""})</span>
                    </>
                  ) : (
                    <>
                      <Play size={13} className="fill-current" />
                      <span>Lanjutkan (#{currentPlayingIndex !== null ? currentPlayingIndex + 1 : 1})</span>
                    </>
                  )
                ) : (
                  <>
                    <Play size={13} className="fill-current" />
                    <span>Putar Semua ({done})</span>
                  </>
                )}
              </button>
            )}

            {busy && (
              <button
                className="rounded-md border border-red-500/50 bg-red-500/20 px-3 py-1.5 text-xs font-semibold text-red-300 hover:bg-red-500/30 hover:border-red-500/70 hover:text-white flex items-center gap-1.5 transition shadow-sm"
                onClick={() => act(() => api.cancelAudio(id))}
                title="Batalkan proses generate audio dan antrean"
              >
                <X size={14} />
                <span>Batal Generate ({generating + queued})</span>
              </button>
            )}
            <button
              className="btn-ghost text-xs flex items-center gap-1.5 text-slate-300 hover:text-white"
              onClick={regenerateAll}
              title="Generate ulang audio untuk semua adegan (termasuk yang sudah selesai)"
            >
              <RotateCcw size={14} className="text-slate-400" /> Ulang Semua Audio
            </button>
            <button
              className="btn-primary text-xs flex items-center gap-1.5 font-semibold"
              disabled={busy}
              onClick={() => act(() => api.generateAudio(id, { mode: "missing" }))}
              title="Generate audio untuk adegan yang belum memiliki audio"
            >
              {busy ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  <span>Memproses Audio ({scenes.filter(s => s.audio_status === 'generating' || s.audio_status === 'queued').length})...</span>
                </>
              ) : done === 0 ? (
                <>
                  <AudioLines size={14} />
                  <span>Generate Semua Audio ({scenes.length})</span>
                </>
              ) : done < scenes.length ? (
                <>
                  <AudioLines size={14} />
                  <span>Generate Sisa Audio ({scenes.length - done})</span>
                </>
              ) : (
                <>
                  <Check size={14} className="text-emerald-300" />
                  <span>Semua Audio Selesai ({scenes.length})</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Play All Controller Strip (muncul saat Play All aktif) */}
        {playingAll && currentPlayingIndex !== null && (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3.5 py-2 text-xs text-amber-200 shadow-inner">
            <div className="flex items-center gap-2.5 min-w-0 flex-1">
              <Volume2 size={16} className={`text-amber-400 shrink-0 ${isPlaying ? "animate-pulse" : "opacity-60"}`} />
              <span className="font-mono font-bold text-amber-300 shrink-0">
                Scene #{currentPlayingIndex + 1}
              </span>
              <span className="text-slate-300 truncate text-xs hidden sm:inline max-w-sm lg:max-w-md">
                "{scenes[currentPlayingIndex]?.narration}"
              </span>
              <span className="font-mono text-[11px] text-amber-300/90 shrink-0 bg-amber-500/15 px-2 py-0.5 rounded border border-amber-500/25 ml-auto sm:ml-0">
                {fmtTime(playCurrentTime)} / {fmtTime(playDuration || scenes[currentPlayingIndex]?.audio_duration || 0)}
              </span>
            </div>

            <div className="flex items-center gap-1.5 shrink-0">
              <button
                className="btn-ghost p-1.5 text-slate-300 hover:text-white disabled:opacity-30"
                onClick={playPrevScene}
                disabled={findPrevPlayable(currentPlayingIndex) === -1}
                title="Scene sebelumnya"
              >
                <SkipBack size={13} />
              </button>
              <button
                className="btn-primary px-3 py-1 text-slate-950 font-bold flex items-center gap-1 text-[11px]"
                onClick={togglePlayPause}
                title={isPlaying ? "Jeda" : "Lanjutkan"}
              >
                {isPlaying ? (
                  <>
                    <Pause size={12} className="fill-current" />
                    <span>Jeda</span>
                  </>
                ) : (
                  <>
                    <Play size={12} className="fill-current" />
                    <span>Putar</span>
                  </>
                )}
              </button>
              <button
                className="btn-ghost p-1.5 text-slate-300 hover:text-white disabled:opacity-30"
                onClick={playNextScene}
                disabled={findNextPlayable(currentPlayingIndex + 1) === -1}
                title="Scene berikutnya"
              >
                <SkipForward size={13} />
              </button>
              <button
                className="btn-ghost px-2 py-1 text-red-300 hover:text-red-200 hover:bg-red-500/20 border-red-500/30 flex items-center gap-1 text-[11px]"
                onClick={stopPlayAll}
                title="Hentikan putar semua audio"
              >
                <Square size={10} className="fill-current" />
                <span>Stop</span>
              </button>
            </div>
          </div>
        )}
        </div>
      </div>

      {/* DAFTAR SCENE */}
      <ul className="space-y-2 mt-2">
        {scenes.map((s, i) => {
          const [label, tone] = STATUS[s.audio_stale ? "stale" : s.audio_status] ?? STATUS.pending;
          const isCurrentPlayAll = currentPlayingIndex === i && playingAll;
          const isGrouped = (s.sentence_group_size ?? 1) > 1;
          const isGroupFirst = s.sentence_group_first ?? true;
          const isGroupLast = s.sentence_group_last ?? true;
          const groupScenes = s.sentence_group_scenes || [i];

          return (
            <div key={i} className={isGrouped && isGroupFirst ? "mt-3 first:mt-0" : ""}>
              {isGrouped && isGroupFirst && (
                <div className="rounded-t-lg bg-gradient-to-r from-emerald-500/15 via-[#181c26] to-[#141720] border-t border-l border-r border-emerald-500/30 shadow-sm overflow-hidden">
                  <div className="flex flex-wrap items-center justify-between gap-2 px-3.5 py-2 border-b border-emerald-500/20 text-[11px] font-mono text-emerald-300/90">
                    <div className="flex items-center gap-2 font-medium">
                      <span className="size-2 rounded-full bg-emerald-400 shadow-sm shadow-emerald-400/50" />
                      <span className="font-bold text-emerald-200">Grup Kalimat #{s.sentence_group + 1}</span>
                      <span className="text-slate-400 text-[10px]">
                        (Scene #{groupScenes[0] + 1} – #{groupScenes[groupScenes.length - 1] + 1} · {s.sentence_group_size} scene digabung saat TTS)
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      {groupScenes.some(idx => scenes[idx]?.audio_status === 'generating' || scenes[idx]?.audio_status === 'queued') ? (
                        <button
                          className="btn-ghost px-2 py-0.5 text-[10px] text-red-300 hover:text-white hover:bg-red-500/20 flex items-center gap-1 border border-red-500/40 rounded transition"
                          onClick={() => act(() => api.cancelAudio(id, groupScenes))}
                          title="Batalkan generate seluruh kalimat ini"
                        >
                          <X size={10} />
                          <span>Batal Grup</span>
                        </button>
                      ) : (
                        <button
                          className="btn-ghost px-2 py-0.5 text-[10px] text-emerald-300 hover:text-white hover:bg-emerald-500/20 flex items-center gap-1 border border-emerald-500/30 rounded transition"
                          onClick={() => act(() => api.generateAudio(id, { mode: "all", indices: groupScenes }))}
                          title="Generate ulang seluruh kalimat ini bersamaan"
                        >
                          <RotateCcw size={10} />
                          <span>Generate Grup</span>
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Combined Group Audio Player */}
                  <div className="flex flex-wrap items-center gap-3 px-3.5 py-2 bg-[#12151d]/90 border-b border-[#292e3b]/50">
                    <div className="flex items-center gap-2 shrink-0">
                      <span className="font-mono text-[9px] uppercase font-bold tracking-wider text-emerald-400 bg-emerald-500/10 border border-emerald-500/30 px-1.5 py-0.5 rounded flex items-center gap-1">
                        <Volume2 size={10} /> Audio Kalimat Utuh
                      </span>
                      <span className="font-mono text-[11px] text-slate-300 font-semibold">
                        {fmtSec(s.sentence_group_duration ?? groupScenes.reduce((acc, idx) => acc + (scenes[idx]?.audio_duration || 0), 0))}
                      </span>
                    </div>

                    {s.sentence_group_status === "done" && s.sentence_group_audio ? (
                      <>
                        <audio
                          controls
                          preload="none"
                          src={api.audioUrl(id, s.sentence_group_audio, s.audio_key)}
                          className="h-8 min-w-0 flex-1"
                          onPlay={() => {
                            if (playingAll) stopPlayAll();
                          }}
                        />
                        <span className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 font-mono text-[10px] text-emerald-400 font-semibold uppercase">
                          SELESAI
                        </span>
                      </>
                    ) : groupScenes.some(idx => scenes[idx]?.audio_status === 'generating') ? (
                      <div className="flex-1 flex items-center gap-2 text-xs text-emerald-300/80 font-mono py-1">
                        <Loader2 size={13} className="animate-spin text-emerald-400" />
                        <span>Sedang memproses audio grup kalimat...</span>
                      </div>
                    ) : groupScenes.some(idx => scenes[idx]?.audio_status === 'queued') ? (
                      <div className="flex-1 text-xs text-amber-300/80 font-mono py-1">
                        Menunggu antrean audio grup...
                      </div>
                    ) : groupScenes.some(idx => scenes[idx]?.audio_status === 'failed') ? (
                      <div className="flex-1 text-xs text-red-300 font-mono py-1">
                        {scenes.find(sc => sc?.audio_error)?.audio_error || "Gagal generate audio grup"}
                      </div>
                    ) : (
                      <div className="flex-1 text-xs text-slate-500 font-mono py-1">
                        Audio kalimat belum dibuat. Klik 'Generate Grup' untuk membuat audio.
                      </div>
                    )}
                  </div>
                </div>
              )}
              <li
                id={`audio-scene-${i}`}
                className={`card flex scroll-mt-72 flex-col gap-3 p-3 sm:flex-row sm:items-center transition-all duration-200 ${
                  isGrouped
                    ? `border-l-4 border-l-emerald-500/80 bg-[#141720]/80 ${
                        isGroupFirst ? "rounded-t-none border-t-0" : ""
                      } ${!isGroupFirst && !isGroupLast ? "rounded-none border-t border-b border-[#292e3b]/30 -mt-2" : ""} ${
                        isGroupLast ? "rounded-t-none -mt-2" : ""
                      }`
                    : ""
                } ${
                  isCurrentPlayAll
                    ? "ring-2 ring-emerald-400 border-emerald-500/70 bg-emerald-500/10 shadow-lg shadow-emerald-500/10"
                    : failedNav.flash === i
                    ? "ring-2 ring-red-400 ring-offset-2 ring-offset-[#0f1117]"
                    : s.audio_status === "failed"
                    ? "border-red-500/40"
                    : ""
                }`}
              >
              <div className="flex items-start gap-3 sm:w-[55%]">
                <div className={`${project.format === "9:16" ? "aspect-[9/16] w-12" : "aspect-video w-24"} shrink-0 overflow-hidden rounded-md bg-[#12141a]`}>
                  {s.image_file && <img src={api.fileUrl(id, s.image_file, project.updated_at)} alt="" className="h-full w-full object-cover" loading="lazy" />}
                </div>
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-bold text-slate-400">#{i + 1}</span>
                    {isGrouped && (
                      <span className="px-1.5 py-0.5 rounded text-[9px] font-mono bg-emerald-500/10 text-emerald-300/80 border border-emerald-500/20" title={`Bagian dari grup kalimat #${s.sentence_group + 1}`}>
                        Grup
                      </span>
                    )}
                    {s.audio_file && s.audio_status === "done" && (
                      <button
                        className={`px-1.5 py-0.5 rounded text-[10px] font-mono flex items-center gap-1 transition ${
                          isCurrentPlayAll && isPlaying
                            ? "bg-emerald-400 text-slate-950 font-bold"
                            : "bg-[#292e3b]/60 text-slate-300 hover:bg-emerald-500/20 hover:text-emerald-300"
                        }`}
                        onClick={() => {
                          if (isCurrentPlayAll) {
                            togglePlayPause();
                          } else {
                            startPlayAll(i);
                          }
                        }}
                        title="Putar audio mulai dari scene ini"
                      >
                        {isCurrentPlayAll && isPlaying ? (
                          <>
                            <Pause size={10} className="fill-current" />
                            <span>Jeda</span>
                          </>
                        ) : (
                          <>
                            <Play size={10} className="fill-current" />
                            <span>Putar dari sini</span>
                          </>
                        )}
                      </button>
                    )}
                  </div>
                  <NarrationText scene={s} onSave={async (text) => setProject(await api.setNarration(id, i, text))} />
                  {s.audio_audit_status === "warning" && (
                    <div
                      onClick={() => setAuditModalScene({ scene: s, index: i, isGrouped, groupScenes })}
                      className="mt-1.5 flex items-start gap-2 rounded-md bg-amber-500/10 border border-amber-500/30 px-2.5 py-1.5 text-xs text-amber-200 cursor-pointer hover:bg-amber-500/20 hover:border-amber-500/50 transition group"
                      title="Klik untuk melihat perbandingan teks vs hasil suara"
                    >
                      <AlertTriangle size={14} className="text-amber-400 shrink-0 mt-0.5" />
                      <div className="flex-1 min-w-0 leading-tight">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span className="font-semibold text-amber-300">Catatan Pelafalan:</span>
                          <span className="text-[11px] text-amber-200/90">{(s.audio_audit_issues ?? []).join(", ") || "Ada ketidaksesuaian kata"}</span>
                        </div>
                        <div className="text-[11px] text-amber-400/80 font-mono mt-0.5 truncate">
                          Didengar Whisper: <span className="italic text-amber-200">"{s.audio_audit_text ?? ""}"</span>
                        </div>
                      </div>
                      <span className="shrink-0 text-[10px] text-amber-400 font-mono font-medium self-center group-hover:text-amber-300 underline">
                        Detail →
                      </span>
                    </div>
                  )}
                </div>
              </div>

              <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2 justify-end sm:justify-start">
                {isGrouped ? (
                  // Inside a group: clean per-scene image duration badge
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    <span className="font-mono text-[11px] text-slate-300 bg-[#1a1e29] px-2.5 py-1 rounded border border-slate-700/50 flex items-center gap-1.5">
                      <span className="text-[10px] text-slate-400 uppercase tracking-wider">Durasi Scene:</span>
                      <b className="text-emerald-400">{fmtSec(s.audio_duration ?? 0)}</b>
                    </span>
                    {isCurrentPlayAll ? (
                      <span className="rounded-md border border-emerald-400/50 bg-emerald-400/20 px-2 py-0.5 font-mono text-[10px] text-emerald-300 font-bold tracking-wider uppercase animate-pulse flex items-center gap-1">
                        <Volume2 size={11} /> SEDANG DIPUTAR
                      </span>
                    ) : (
                      <span className={`rounded-md border px-2 py-0.5 font-mono text-[10px] tracking-wider uppercase font-semibold ${tone}`}>
                        {label}
                      </span>
                    )}
                    {s.audio_audit_status === "warning" ? (
                      <button
                        type="button"
                        onClick={() => setAuditModalScene({ scene: s, index: i, isGrouped, groupScenes })}
                        className="rounded-md border border-amber-500/50 bg-amber-500/15 hover:bg-amber-500/30 px-2 py-0.5 font-mono text-[10px] text-amber-300 font-semibold flex items-center gap-1 transition cursor-pointer shadow-xs active:scale-95"
                        title="Klik untuk melihat perbandingan teks naskah vs yang didengar Whisper"
                      >
                        <AlertTriangle size={10} className="text-amber-400" />
                        <span>Cek Pelafalan</span>
                      </button>
                    ) : s.audio_audit_status === "ok" ? (
                      <button
                        type="button"
                        onClick={() => setAuditModalScene({ scene: s, index: i, isGrouped, groupScenes })}
                        className="rounded border border-emerald-500/30 bg-emerald-500/10 hover:bg-emerald-500/25 px-1.5 py-0.5 font-mono text-[9px] text-emerald-400/90 flex items-center gap-1 transition cursor-pointer"
                        title="Klik untuk melihat perbandingan teks naskah vs yang didengar Whisper"
                      >
                        <CheckCircle2 size={9} />
                        <span>{Math.round((s.audio_audit_score ?? 1) * 100)}%</span>
                      </button>
                    ) : null}
                  </div>
                ) : (
                  // Standalone scene: individual audio player
                  <>
                    {s.audio_file && s.audio_status === "done" ? (
                      <>
                        <audio
                          controls
                          preload="none"
                          src={api.audioUrl(id, s.audio_file, s.audio_key)}
                          className="h-8 min-w-0 flex-1"
                          onPlay={() => {
                            if (playingAll) stopPlayAll();
                          }}
                        />
                        <span className="font-mono text-[11px] text-slate-400">{fmtSec(s.audio_duration ?? 0)}</span>
                      </>
                    ) : (
                      <span className="flex-1 text-xs text-red-300">{s.audio_error}</span>
                    )}

                    {isCurrentPlayAll ? (
                      <span className="rounded-md border border-amber-400/50 bg-amber-400/20 px-2 py-0.5 font-mono text-[10px] text-amber-300 font-bold tracking-wider uppercase animate-pulse flex items-center gap-1">
                        <Volume2 size={11} /> SEDANG DIPUTAR
                      </span>
                    ) : (
                      <span className={`rounded-md border px-2 py-0.5 font-mono text-[10px] tracking-wider uppercase font-semibold ${tone}`}>
                        {label}
                      </span>
                    )}
                    {s.audio_audit_status === "warning" ? (
                      <button
                        type="button"
                        onClick={() => setAuditModalScene({ scene: s, index: i, isGrouped: false, groupScenes: [i] })}
                        className="rounded-md border border-amber-500/50 bg-amber-500/15 hover:bg-amber-500/30 px-2 py-0.5 font-mono text-[10px] text-amber-300 font-semibold flex items-center gap-1 transition cursor-pointer shadow-xs active:scale-95"
                        title="Klik untuk melihat perbandingan teks naskah vs yang didengar Whisper"
                      >
                        <AlertTriangle size={10} className="text-amber-400" />
                        <span>Cek Pelafalan</span>
                      </button>
                    ) : s.audio_audit_status === "ok" ? (
                      <button
                        type="button"
                        onClick={() => setAuditModalScene({ scene: s, index: i, isGrouped: false, groupScenes: [i] })}
                        className="rounded border border-emerald-500/30 bg-emerald-500/10 hover:bg-emerald-500/25 px-1.5 py-0.5 font-mono text-[9px] text-emerald-400/90 flex items-center gap-1 transition cursor-pointer"
                        title="Klik untuk melihat perbandingan teks naskah vs yang didengar Whisper"
                      >
                        <CheckCircle2 size={9} />
                        <span>{Math.round((s.audio_audit_score ?? 1) * 100)}%</span>
                      </button>
                    ) : null}

                    {s.audio_status === "generating" ? (
                      <div className="flex items-center gap-1.5">
                        <button
                          className="btn-ghost px-2.5 py-1 text-[11px] text-amber-300 opacity-80 cursor-wait flex items-center gap-1.5"
                          disabled
                        >
                          <Loader2 size={12} className="animate-spin text-amber-400" />
                          <span>Memproses...</span>
                        </button>
                        <button
                          className="rounded border border-red-500/40 bg-red-500/10 px-2 py-1 text-[11px] text-red-300 hover:bg-red-500/25 hover:text-white flex items-center gap-1 transition"
                          onClick={() => act(() => api.cancelAudio(id, [i]))}
                          title="Batalkan generate scene ini"
                        >
                          <X size={11} />
                          <span>Batal</span>
                        </button>
                      </div>
                    ) : s.audio_status === "queued" ? (
                      <div className="flex items-center gap-1.5">
                        <button
                          className="rounded border border-red-500/40 bg-red-500/10 px-2.5 py-1 text-[11px] text-red-300 hover:bg-red-500/25 hover:text-white flex items-center gap-1 transition font-medium"
                          onClick={() => act(() => api.cancelAudio(id, [i]))}
                          title="Batalkan antrean scene ini"
                        >
                          <X size={12} />
                          <span>Batal Antre</span>
                        </button>
                      </div>
                    ) : s.audio_file && s.audio_status === "done" && !s.audio_stale ? (
                      <button
                        className="btn-ghost px-2.5 py-1 text-[11px] text-slate-300 hover:text-white flex items-center gap-1.5 transition"
                        onClick={() => act(() => api.generateAudio(id, { mode: "all", indices: [i] }))}
                        title="Generate ulang audio untuk scene ini"
                      >
                        <RotateCcw size={12} className="text-slate-400" />
                        <span>Generate Ulang</span>
                      </button>
                    ) : s.audio_status === "failed" ? (
                      <button
                        className="rounded-md border border-red-500/40 bg-red-500/10 px-2.5 py-1 text-[11px] font-medium text-red-300 hover:bg-red-500/20 hover:border-red-500/60 flex items-center gap-1.5 transition"
                        onClick={() => act(() => api.generateAudio(id, { mode: "all", indices: [i] }))}
                        title="Coba generate ulang audio yang gagal"
                      >
                        <RotateCcw size={12} />
                        <span>Coba Lagi</span>
                      </button>
                    ) : (
                      <button
                        className="rounded-md border border-amber-500/40 bg-amber-500/10 px-2.5 py-1 text-[11px] font-semibold text-amber-300 hover:bg-amber-500/20 hover:border-amber-500/60 flex items-center gap-1.5 transition shadow-sm"
                        onClick={() => act(() => api.generateAudio(id, { mode: "all", indices: [i] }))}
                        title="Generate audio untuk scene ini"
                      >
                        <AudioLines size={12} className="text-amber-400" />
                        <span>Generate Audio</span>
                      </button>
                    )}
                  </>
                )}
              </div>
            </li>
            </div>
          );
        })}
      </ul>

      {/* FLOATING SCROLL TO TOP BUTTON DI KANAN BAWAH */}
      <button
        onClick={scrollToTop}
        className={`fixed bottom-6 right-6 z-40 flex items-center gap-2 rounded-full border border-amber-500/40 bg-[#161920]/95 px-4 py-2.5 font-semibold text-xs text-amber-300 shadow-2xl backdrop-blur-md transition-all duration-300 hover:bg-amber-500 hover:text-slate-950 hover:border-amber-400 hover:scale-105 active:scale-95 ${
          showScrollTop
            ? "translate-y-0 opacity-100 pointer-events-auto shadow-amber-500/20"
            : "translate-y-4 opacity-0 pointer-events-none"
        }`}
        title="Kembali ke atas halaman"
        aria-label="Scroll ke atas"
      >
        <ChevronUp size={16} strokeWidth={2.5} />
        <span>Ke Atas</span>
      </button>

      <FailedNav nav={failedNav} noun="audio" />
      <VoiceLibrary
        open={libraryOpen}
        onClose={() => {
          setLibraryOpen(false);
          api.settings().then(setSettings).catch(() => {});
        }}
        onChanged={setVoices}
      />

      {auditModalScene && (
        <AuditModal
          data={auditModalScene}
          onClose={() => setAuditModalScene(null)}
          onRegenerate={(data) => {
            const indices = data.isGrouped && data.groupScenes?.length ? data.groupScenes : [data.index];
            act(() => api.generateAudio(id, { mode: "all", indices }));
          }}
        />
      )}
    </div>
  );
}
