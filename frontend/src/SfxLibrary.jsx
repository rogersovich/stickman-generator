import { Dialog, DialogBackdrop, DialogPanel, DialogTitle } from "@headlessui/react";
import { Check, CloudUpload, Loader2, Pause, Play, Search, Trash2, Volume2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import { useDialog } from "./ui.jsx";

const CATEGORIES = [
  ["all", "Semua"],
  ["transition", "Transisi"],
  ["reaction", "Reaksi"],
  ["action", "Aksi"],
  ["impact", "Impact"],
  ["dramatic", "Dramatis"],
  ["custom", "Upload"],
];

function readBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1]);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

// One shared preview player, so starting a clip stops the previous one (also used by ExportView).
let player = null;
export function playSfx(item, onEnd) {
  player?.pause();
  player = new Audio(api.sfxAudioUrl(item.id));
  player.volume = Math.max(0, Math.min(1, item.volume ?? 1));
  player.onended = player.onerror = () => onEnd?.();
  player.play().catch(() => onEnd?.());
}
export function stopSfx() {
  player?.pause();
  player = null;
}

// Modal: the sound-effect library (preview, volume, upload, delete). With `selectedId !== undefined`
// it is also a picker: "Pakai" calls onPick(id) for the scene being edited.
export default function SfxLibrary({ open, onClose, onChanged, title, selectedId, onPick }) {
  const dialog = useDialog();
  const fileRef = useRef(null);
  const [items, setItems] = useState([]);
  const [query, setQuery] = useState("");
  const [cat, setCat] = useState("all");
  const [playingId, setPlayingId] = useState(null);
  const [busy, setBusy] = useState("");
  const [dragging, setDragging] = useState(false);
  const picking = typeof onPick === "function";

  async function refresh() {
    const list = await api.sfx();
    setItems(list);
    onChanged?.(list);
  }

  useEffect(() => {
    if (open) refresh().catch(() => {});
    else {
      stopSfx();
      setPlayingId(null);
    }
  }, [open]);

  function togglePlay(item) {
    if (playingId === item.id) {
      stopSfx();
      setPlayingId(null);
      return;
    }
    setPlayingId(item.id);
    playSfx(item, () => setPlayingId((cur) => (cur === item.id ? null : cur)));
  }

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

  const upload = (file) =>
    run("upload", async () => {
      await api.uploadSfx({ audio_base64: await readBase64(file), filename: file.name, volume: 0.85 });
      if (fileRef.current) fileRef.current.value = "";
      setCat("all");
      await refresh();
    });

  function onDrop(e) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (!file || busy) return;
    if (!file.type.startsWith("audio/") && !/\.(mp3|wav|m4a|aac|ogg|opus|flac|aiff?)$/i.test(file.name)) {
      dialog.alert({ title: "Bukan file audio", message: `"${file.name}" bukan file audio. Pakai MP3, WAV, M4A, OGG, dsb.` });
      return;
    }
    upload(file);
  }

  // volume edits are local while dragging, saved on release
  function setLocalVolume(id, volume) {
    setItems((list) => list.map((x) => (x.id === id ? { ...x, volume } : x)));
  }
  const saveVolume = (item) => run(`vol-${item.id}`, async () => (await api.updateSfx(item.id, { volume: item.volume }), await refresh()));

  async function remove(item) {
    const ok = await dialog.confirm({
      title: `Hapus SFX "${item.label}"?`,
      message: "File-nya ikut terhapus. Adegan yang memakai SFX ini tidak akan berbunyi saat diekspor.",
      confirmLabel: "Hapus",
      danger: true,
    });
    if (!ok) return;
    if (playingId === item.id) stopSfx();
    run(`del-${item.id}`, async () => (await api.deleteSfx(item.id), await refresh()));
  }

  const q = query.trim().toLowerCase();
  const shown = items.filter(
    (x) => (cat === "all" || x.category === cat) && (!q || x.label.toLowerCase().includes(q) || x.desc.toLowerCase().includes(q))
  );

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
              <DialogTitle className="text-lg font-bold text-slate-100">{title || "Library SFX"}</DialogTitle>
              <p className="mt-1 text-xs text-slate-400">
                Efek suara masuk ke track audio sendiri di CapCut, di awal atau akhir adegan. Volume berlaku untuk semua project.
              </p>
            </div>
            <button className="rounded-lg p-1.5 text-slate-400 hover:bg-[#1e222b] hover:text-slate-200" onClick={onClose} aria-label="Tutup">
              <X size={18} />
            </button>
          </div>

          <div className="space-y-2.5">
            <div className="relative">
              <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
              <input className="input pl-9" placeholder="Cari SFX…" value={query} onChange={(e) => setQuery(e.target.value)} />
            </div>
            <div className="flex flex-wrap gap-1.5">
              {CATEGORIES.map(([key, label]) => (
                <button
                  key={key}
                  className={`whitespace-nowrap rounded-md border px-2.5 py-1 text-[11px] transition ${
                    cat === key
                      ? "border-amber-500 bg-amber-500/15 font-semibold text-amber-300"
                      : "border-[#292e3b] text-slate-400 hover:bg-[#1e222b] hover:text-slate-200"
                  }`}
                  onClick={() => setCat(key)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          <ul className="min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
            {shown.length === 0 && (
              <li className="rounded-xl border border-dashed border-[#292e3b] p-5 text-center text-sm text-slate-400">
                {items.length === 0 ? "Memuat…" : "Tidak ada SFX yang cocok."}
              </li>
            )}
            {shown.map((item) => {
              const isPlaying = playingId === item.id;
              const isSelected = picking && selectedId === item.id;
              return (
                <li key={item.id} className={`card flex flex-wrap items-center gap-3 p-3 ${isSelected ? "border-amber-500/50" : ""}`}>
                  <button
                    className={`rounded-full border p-2 transition ${
                      isPlaying
                        ? "border-amber-400 bg-amber-400 text-slate-900 shadow-md shadow-amber-400/20"
                        : "border-[#292e3b] text-amber-300 hover:bg-amber-500/10"
                    }`}
                    onClick={() => togglePlay(item)}
                    aria-label={`${isPlaying ? "Hentikan" : "Putar"} ${item.label}`}
                  >
                    {isPlaying ? <Pause size={13} /> : <Play size={13} />}
                  </button>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 text-sm font-semibold text-slate-100">
                      <span className="truncate">{item.label}</span>
                      <span className="font-mono text-[11px] font-normal text-slate-500">{item.duration.toFixed(1)} dtk</span>
                    </div>
                    <p className="truncate text-xs text-slate-400">{item.desc}</p>
                  </div>
                  <label className="flex items-center gap-1.5 text-slate-400" title="Volume SFX di CapCut">
                    <Volume2 size={13} />
                    <input
                      type="range"
                      min="0"
                      max="1"
                      step="0.05"
                      value={item.volume}
                      onChange={(e) => setLocalVolume(item.id, parseFloat(e.target.value))}
                      onPointerUp={() => saveVolume(item)}
                      onKeyUp={() => saveVolume(item)}
                      className="w-20 accent-amber-500"
                      aria-label={`Volume ${item.label}`}
                    />
                    <span className="w-8 text-right font-mono text-[11px]">{Math.round(item.volume * 100)}%</span>
                  </label>
                  {!item.built_in && (
                    <button
                      className="rounded-lg p-1.5 text-slate-400 hover:bg-red-500/15 hover:text-red-300"
                      onClick={() => remove(item)}
                      disabled={!!busy}
                      aria-label={`Hapus SFX ${item.label}`}
                    >
                      <Trash2 size={14} />
                    </button>
                  )}
                  {picking && (
                    <button
                      className={isSelected ? "btn-ghost px-2.5 py-1 text-[11px] text-amber-300" : "btn-primary px-2.5 py-1 text-[11px]"}
                      onClick={() => onPick(item.id)}
                    >
                      {isSelected ? <Check size={12} /> : null} {isSelected ? "Dipakai" : "Pakai"}
                    </button>
                  )}
                </li>
              );
            })}
          </ul>

          <div className="space-y-2.5 border-t border-[#292e3b] pt-4">
            <input
              ref={fileRef}
              type="file"
              accept="audio/*"
              className="hidden"
              onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
            />
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              disabled={!!busy}
              className={`flex w-full items-center justify-center gap-3 rounded-xl border-2 border-dashed px-4 py-4 text-left transition *:pointer-events-none ${
                dragging
                  ? "border-amber-400 bg-amber-500/10 text-amber-200"
                  : "border-[#292e3b] text-slate-400 hover:border-amber-500/50 hover:bg-[#1e222b]/60 hover:text-slate-200"
              }`}
            >
              {busy === "upload" ? (
                <Loader2 size={22} className="shrink-0 animate-spin text-amber-400" />
              ) : (
                <CloudUpload size={22} className="shrink-0 text-amber-400" />
              )}
              <span>
                <span className="block text-sm font-semibold text-slate-200">
                  {busy === "upload" ? "Mengunggah SFX…" : dragging ? "Lepas file di sini" : "Tarik & lepas file audio, atau klik untuk pilih"}
                </span>
                <span className="block text-[11px] text-slate-500">MP3/WAV/M4A/OGG, maksimal 30 detik</span>
              </span>
            </button>
            {picking && selectedId && (
              <div className="flex justify-end">
                <button className="btn-ghost text-xs text-red-300" onClick={() => onPick(null)}>
                  <X size={14} /> Lepas SFX adegan ini
                </button>
              </div>
            )}
          </div>
        </DialogPanel>
      </div>
    </Dialog>
  );
}
