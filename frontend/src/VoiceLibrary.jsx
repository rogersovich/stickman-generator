import { Dialog, DialogBackdrop, DialogPanel, DialogTitle } from "@headlessui/react";
import { Download, Loader2, Pause, Play, Star, Trash2, Upload, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import { useDialog } from "./ui.jsx";

function readBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1]);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

// Modal: the voice library shared by every project (upload, preview, delete, set default, import).
export default function VoiceLibrary({ open, onClose, onChanged }) {
  const dialog = useDialog();
  const fileRef = useRef(null);
  const audioRef = useRef(null);
  const [voices, setVoices] = useState([]);
  const [defaultId, setDefaultId] = useState(null);
  const [playingId, setPlayingId] = useState(null);
  const [name, setName] = useState("");
  const [transcript, setTranscript] = useState("");
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState("");

  function stopAudio() {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    setPlayingId(null);
  }

  function togglePlay(id) {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    if (playingId === id) {
      setPlayingId(null);
      return;
    }
    const audio = new Audio(api.voiceAudioUrl(id));
    audioRef.current = audio;
    setPlayingId(id);
    audio.play().catch(() => {
      setPlayingId(null);
      audioRef.current = null;
    });
    audio.onended = () => {
      setPlayingId(null);
      audioRef.current = null;
    };
    audio.onerror = () => {
      setPlayingId(null);
      audioRef.current = null;
    };
  }

  async function refresh() {
    const [list, s] = await Promise.all([api.voices(), api.settings()]);
    setVoices(list);
    setDefaultId(s.tts_voice_id);
    onChanged?.(list);
  }

  useEffect(() => {
    if (open) refresh().catch(() => {});
    else stopAudio();
  }, [open]);

  useEffect(() => {
    return () => stopAudio();
  }, []);

  async function run(label, fn) {
    setBusy(label);
    try {
      await fn();
    } catch (e) {
      await dialog.alert({ title: "Gagal", message: e.message });
    } finally {
      setBusy("");
    }
  }

  const upload = (e) =>
    run("upload", async () => {
      e.preventDefault();
      await api.createVoice({ name, transcript, audio_base64: await readBase64(file), filename: file.name });
      setName("");
      setTranscript("");
      setFile(null);
      if (fileRef.current) fileRef.current.value = "";
      await refresh();
    });

  const importLegacy = () =>
    run("import", async () => {
      const { imported } = await api.importLegacyVoices();
      await refresh();
      await dialog.alert({ title: "Impor selesai", message: `${imported} suara baru diimpor dari manhwa-recap-studio.` });
    });

  const setDefault = (id) =>
    run(`default-${id}`, async () => {
      const s = await api.settings();
      await api.saveSettings({ ...s, tts_voice_id: id });
      await refresh();
    });

  async function remove(v) {
    const ok = await dialog.confirm({
      title: `Hapus suara "${v.name}"?`,
      message: "Rekaman referensinya ikut terhapus. Project yang memakai suara ini perlu memilih suara lain.",
      confirmLabel: "Hapus",
      danger: true,
    });
    if (ok) {
      if (playingId === v.id) stopAudio();
      run(`del-${v.id}`, async () => (await api.deleteVoice(v.id), await refresh()));
    }
  }

  return (
    <Dialog open={open} onClose={onClose} className="relative z-50">
      <DialogBackdrop transition className="fixed inset-0 bg-black/70 backdrop-blur-sm duration-150 data-closed:opacity-0" />
      <div className="fixed inset-0 flex items-center justify-center p-4">
        <DialogPanel
          transition
          className="flex max-h-[90vh] w-full max-w-2xl flex-col gap-4 rounded-2xl border border-[#292e3b] bg-[#161920] p-6 shadow-2xl duration-150 data-closed:scale-95 data-closed:opacity-0"
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <DialogTitle className="text-lg font-bold text-slate-100">Library Suara</DialogTitle>
              <p className="mt-1 text-xs text-slate-400">Rekaman referensi 1–11,5 detik. Model meniru suara ini untuk narasi.</p>
            </div>
            <button className="rounded-lg p-1.5 text-slate-400 hover:bg-[#1e222b] hover:text-slate-200" onClick={onClose} aria-label="Tutup">
              <X size={18} />
            </button>
          </div>

          <ul className="min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
            {voices.length === 0 && (
              <li className="rounded-xl border border-dashed border-[#292e3b] p-5 text-center text-sm text-slate-400">
                Belum ada suara. Upload rekaman atau impor dari manhwa-recap-studio.
              </li>
            )}
            {voices.map((v) => {
              const isPlaying = playingId === v.id;
              return (
                <li key={v.id} className="card flex items-center gap-3 p-3">
                  <button
                    className={`rounded-full border p-2 transition ${
                      isPlaying
                        ? "border-amber-400 bg-amber-400 text-slate-900 shadow-md shadow-amber-400/20"
                        : "border-[#292e3b] text-amber-300 hover:bg-amber-500/10"
                    }`}
                    onClick={() => togglePlay(v.id)}
                    title={isPlaying ? "Hentikan contoh" : "Putar contoh"}
                    aria-label={`${isPlaying ? "Hentikan" : "Putar"} contoh suara ${v.name}`}
                  >
                    {isPlaying ? <Pause size={13} /> : <Play size={13} />}
                  </button>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 text-sm font-semibold text-slate-100">
                      {v.name}
                      {v.id === defaultId && <span className="rounded bg-amber-500/15 px-1.5 font-mono text-[10px] text-amber-300">DEFAULT</span>}
                      <span className="font-mono text-[11px] font-normal text-slate-500">{v.duration.toFixed(1)} dtk</span>
                    </div>
                    {v.transcript && <p className="truncate text-xs text-slate-400">{v.transcript}</p>}
                  </div>
                  {v.id !== defaultId && (
                    <button className="btn-ghost px-2 py-1 text-[11px]" onClick={() => setDefault(v.id)} disabled={!!busy} title="Jadikan suara default">
                      <Star size={12} /> Default
                    </button>
                  )}
                  <button
                    className="rounded-lg p-1.5 text-slate-400 hover:bg-red-500/15 hover:text-red-300"
                    onClick={() => remove(v)}
                    disabled={!!busy}
                    aria-label={`Hapus suara ${v.name}`}
                  >
                    <Trash2 size={14} />
                  </button>
                </li>
              );
            })}
          </ul>

          <form onSubmit={upload} className="space-y-2.5 border-t border-[#292e3b] pt-4">
            <div className="grid gap-2.5 sm:grid-cols-2">
              <input className="input" placeholder="Nama suara" value={name} onChange={(e) => setName(e.target.value)} maxLength={60} required />
              <input ref={fileRef} className="input text-xs" type="file" accept="audio/*" onChange={(e) => setFile(e.target.files?.[0] ?? null)} required />
            </div>
            <input
              className="input"
              placeholder="Transkrip rekaman (opsional, membantu OmniVoice)"
              value={transcript}
              onChange={(e) => setTranscript(e.target.value)}
            />
            <div className="flex flex-wrap gap-2">
              <button className="btn-primary text-xs" disabled={!!busy || !file || !name.trim()}>
                {busy === "upload" ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />} Upload suara
              </button>
              <button type="button" className="btn-ghost ml-auto text-xs" onClick={importLegacy} disabled={!!busy}>
                {busy === "import" ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />} Impor dari manhwa-recap-studio
              </button>
            </div>
          </form>
        </DialogPanel>
      </div>
    </Dialog>
  );
}
