import { useState } from "react";
import { ChevronDown, ChevronUp, Clock, Eye, Film, Layers, Plus, Save, Sparkles, Trash2, WandSparkles } from "lucide-react";
import { api } from "./api.js";
import NarrationEditor from "./NarrationEditor.jsx";
import { useDialog } from "./ui.jsx";

const EMPTY_SCENE = {
  narration: "",
  scene_description: "",
  title_text: "",
  prompt: "",
  tag: "",
  is_merged: false,
  merged_with: null,
};

function pick({ narration, scene_description, title_text, prompt, tag, is_merged, merged_with }) {
  return {
    narration: narration ?? "",
    scene_description: scene_description ?? "",
    title_text: title_text ?? "",
    prompt: prompt ?? "",
    tag: tag ?? "",
    is_merged: is_merged ?? false,
    merged_with: merged_with ?? null,
  };
}

export default function DraftEditor({ project, onConfirmed }) {
  const dialog = useDialog();
  const [title, setTitle] = useState(project.title);
  const [coreAnswer, setCoreAnswer] = useState(project.core_answer ?? "");
  const [scenes, setScenes] = useState(project.scenes.map(pick));
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [prompts, setPrompts] = useState(null);
  const [narrationIndex, setNarrationIndex] = useState(null);

  function update(next) {
    setScenes(next);
    setDirty(true);
    setPrompts(null);
  }
  const edit = (i, key) => (e) => update(scenes.map((s, j) => (j === i ? { ...s, [key]: e.target.value } : s)));
  const remove = (i) => update(scenes.filter((_, j) => j !== i));
  const insertAfter = (i) => update([...scenes.slice(0, i + 1), { ...EMPTY_SCENE }, ...scenes.slice(i + 1)]);
  function move(i, d) {
    const j = i + d;
    if (j < 0 || j >= scenes.length) return;
    const next = [...scenes];
    [next[i], next[j]] = [next[j], next[i]];
    update(next);
  }

  async function save() {
    await api.updateDraft(project.id, { title, core_answer: coreAnswer, scenes });
    setDirty(false);
  }

  async function run(label, fn) {
    setBusy(label);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  }

  const words = scenes.reduce((n, s) => n + s.narration.split(/\s+/).filter(Boolean).length, 0);
  const estSeconds = Math.round(words / 2.5);
  const generateCount = scenes.filter((s) => !s.is_merged).length;

  return (
    <div className="space-y-6 pb-32">
      {/* Top Storyboard Header */}
      <div className="panel p-6 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#292e3b] pb-3 text-xs font-mono text-slate-400">
          <div className="flex items-center gap-2">
            <span className="rounded bg-amber-500/10 px-2 py-0.5 text-amber-300 font-semibold border border-amber-500/20">
              DRAFT
            </span>
            <span className="rounded border border-[#292e3b] bg-[#1e222b] px-2 py-0.5">
              {project.format}
            </span>
            <span className="rounded border border-[#292e3b] bg-[#1e222b] px-2 py-0.5">
              {scenes.length} adegan ({generateCount} gambar)
            </span>
            {project.story_model && (
              <span className="rounded border border-[#292e3b] bg-[#1e222b] px-2 py-0.5 text-slate-400">
                {project.story_model}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1.5 text-slate-400">
            <Clock size={13} className="text-amber-400" />
            <span>±{Math.floor(estSeconds / 60)}m {estSeconds % 60}s ({words} kata)</span>
          </div>
        </div>

        <div>
          <label className="label">Judul Project Cerita</label>
          <input
            className="input text-base font-bold text-slate-100"
            value={title}
            onChange={(e) => {
              setTitle(e.target.value);
              setDirty(true);
            }}
          />
        </div>

        {coreAnswer && (
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4 space-y-2">
            <div className="flex items-center justify-between">
              <label className="label text-amber-300 mb-0">Premis & Catatan Inti</label>
              <span className="text-[11px] text-amber-400/80 font-mono">Pilar Cerita</span>
            </div>
            <textarea
              className="input min-h-16 leading-relaxed border-amber-500/30 bg-[#12141a] text-slate-100 focus:border-amber-400"
              value={coreAnswer}
              onChange={(e) => {
                setCoreAnswer(e.target.value);
                setDirty(true);
              }}
            />
          </div>
        )}
      </div>

      {/* Storyboard Reel Card Stack */}
      <div className="space-y-4">
        <div className="flex items-center justify-between px-1">
          <h3 className="flex items-center gap-2 text-xs font-bold tracking-wider text-slate-400 uppercase">
            <Film size={14} className="text-amber-400" />
            Papan Adegan Storyboard ({scenes.length})
          </h3>
          <span className="text-xs text-slate-400">
            {generateCount} gambar unik · {scenes.length - generateCount} adegan split-screen gabung
          </span>
        </div>

        {scenes.map((s, i) => {
          const sceneWords = s.narration.split(/\s+/).filter(Boolean).length;
          const sceneSec = Math.round(sceneWords / 2.5);

          return (
            <div key={i} className="card p-5 space-y-4 transition-all hover:border-[#3d4455]">
              {/* Scene Frame Ribbon */}
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#292e3b] pb-3">
                <div className="flex items-center gap-2.5">
                  <span className="rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 font-mono text-xs font-semibold text-amber-300">
                    SCENE {String(i + 1).padStart(2, "0")}
                  </span>
                  {s.tag && (
                    <span className="rounded border border-[#292e3b] bg-[#161920] px-2 py-0.5 font-mono text-[11px] text-slate-300">
                      {s.tag}
                    </span>
                  )}
                  {s.is_merged && (
                    <span className="rounded border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 font-mono text-[11px] text-amber-300 font-semibold">
                      [DUAL SPLIT-SCREEN]
                    </span>
                  )}
                  <span className="font-mono text-xs text-slate-400">
                    ±{sceneSec}s ({sceneWords} kata)
                  </span>
                </div>

                <div className="flex items-center gap-1.5">
                  <button
                    className="btn-ghost size-8 p-0"
                    onClick={() => move(i, -1)}
                    disabled={i === 0}
                    aria-label="Geser adegan ke atas"
                    title="Geser ke atas"
                  >
                    <ChevronUp size={15} />
                  </button>
                  <button
                    className="btn-ghost size-8 p-0"
                    onClick={() => move(i, 1)}
                    disabled={i === scenes.length - 1}
                    aria-label="Geser adegan ke bawah"
                    title="Geser ke bawah"
                  >
                    <ChevronDown size={15} />
                  </button>
                  <button
                    className="btn-ghost px-2.5 py-1 text-xs"
                    onClick={() => insertAfter(i)}
                    title="Sisipkan adegan baru di bawah"
                  >
                    <Plus size={13} className="text-amber-400" /> Sisip
                  </button>
                  <button
                    className="btn-danger size-8 p-0 text-red-400"
                    onClick={() => remove(i)}
                    disabled={scenes.length === 1}
                    aria-label="Hapus adegan ini"
                    title="Hapus adegan"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>

              {/* Merged Scene Notice */}
              {s.is_merged && (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200">
                  Gambar adegan ini otomatis disatukan dengan <b>Scene {(s.merged_with ?? i - 1) + 1}</b> (panel split-screen). Tidak memotong kredit antrian gambar baru di Flow.
                </div>
              )}

              {/* Dual Zone Script Block */}
              <div className="grid gap-4 lg:grid-cols-2">
                {/* Voiceover Narration (Beat Narasi) */}
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <label className="label mb-0">Beat Narasi Suara</label>
                    <button
                      className="inline-flex items-center gap-1 text-xs font-medium text-amber-400 hover:text-amber-300 disabled:opacity-40 transition-colors"
                      disabled={!!busy || !s.narration.trim()}
                      onClick={() =>
                        run("ai", async () => {
                          if (dirty) await save();
                          setNarrationIndex(i);
                        })
                      }
                    >
                      <WandSparkles size={13} /> Edit dengan AI
                    </button>
                  </div>
                  <textarea
                    className="input min-h-32 leading-relaxed"
                    value={s.narration}
                    placeholder="Tulis atau edit narasi adegan..."
                    onChange={edit(i, "narration")}
                  />
                </div>

                {/* Visual Direction / Flow Prompt */}
                <div className="space-y-3">
                  {s.prompt ? (
                    <div>
                      <div className="flex items-center justify-between">
                        <label className="label mb-0">Prompt Google Flow (Lengkap)</label>
                        <span className="font-mono text-[10px] text-slate-400">Auto-inject ke Flow</span>
                      </div>
                      <textarea
                        className="input min-h-32 font-mono text-xs leading-relaxed text-amber-200/90"
                        value={s.prompt}
                        placeholder="CREATE IMAGE..."
                        onChange={edit(i, "prompt")}
                      />
                    </div>
                  ) : (
                    <>
                      <div>
                        <label className="label">Visual Prompt (English ke Google Flow)</label>
                        <textarea
                          className="input min-h-20 leading-relaxed font-mono text-xs text-slate-300"
                          value={s.scene_description}
                          placeholder="e.g. A minimalist stickman teacher..."
                          onChange={edit(i, "scene_description")}
                        />
                      </div>
                      <div>
                        <label className="label">
                          Teks Judul di Gambar <span className="text-slate-400 font-normal lowercase">(opsional)</span>
                        </label>
                        <input
                          className="input"
                          value={s.title_text}
                          placeholder="Contoh: KOTA HILANG DITEMUKAN"
                          onChange={edit(i, "title_text")}
                        />
                      </div>
                    </>
                  )}
                </div>
              </div>

              {/* Only show compiled prompt preview for AI mode where s.prompt is not directly defined */}
              {!s.prompt && prompts?.[i] && (
                <div className="rounded-lg border border-[#292e3b] bg-[#12141a] p-3 text-xs">
                  <div className="mb-1 text-[11px] font-mono text-slate-400 uppercase tracking-wider">Hasil Prompt Akhir:</div>
                  <pre className="max-h-40 overflow-auto font-mono text-xs whitespace-pre-wrap text-amber-200/90">
                    {prompts[i]}
                  </pre>
                </div>
              )}
            </div>
          );
        })}
      </div>

      <NarrationEditor
        open={narrationIndex !== null}
        onClose={() => setNarrationIndex(null)}
        projectId={project.id}
        index={narrationIndex ?? 0}
        current={scenes[narrationIndex ?? 0]?.narration ?? ""}
        onApply={async (text) => update(scenes.map((sc, j) => (j === narrationIndex ? { ...sc, narration: text } : sc)))}
      />

      {/* Floating Action Dock */}
      <div className="fixed inset-x-0 bottom-0 z-40 border-t border-[#292e3b] bg-[#0e1015]/95 backdrop-blur-md">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-4 py-3.5">
          <div className="flex items-center gap-2 text-xs">
            {error ? (
              <span className="font-medium text-red-400">{error}</span>
            ) : dirty ? (
              <span className="flex items-center gap-1.5 text-amber-400">
                <span className="size-2 rounded-full bg-amber-400 animate-pulse" />
                Ada perubahan belum disimpan
              </span>
            ) : (
              <span className="flex items-center gap-1.5 text-slate-400">
                <span className="size-2 rounded-full bg-emerald-400" />
                Semua draf tersimpan rapi
              </span>
            )}
          </div>

          <div className="flex items-center gap-2.5">
            <button className="btn-ghost" disabled={!!busy || !dirty} onClick={() => run("save", save)}>
              <Save size={15} /> {busy === "save" ? "Menyimpan…" : "Simpan Draf"}
            </button>

            <button
              className="btn-ghost"
              disabled={!!busy}
              onClick={() =>
                run("prompts", async () => {
                  if (dirty) await save();
                  setPrompts(await api.prompts(project.id));
                })
              }
            >
              <Eye size={15} /> Lihat Prompt
            </button>

            <button
              className="btn-primary"
              disabled={!!busy}
              onClick={() =>
                run("confirm", async () => {
                  const ok = await dialog.confirm({
                    title: `Generate ${generateCount} frame di Google Flow?`,
                    message:
                      `Draf naskah (${scenes.length} adegan) akan dikunci. ${generateCount} gambar akan dibuat satu per satu di Flow. Pastikan worker di extension sudah ON.`,
                    confirmLabel: "Ya, Mulai Generate",
                  });
                  if (!ok) return;
                  if (dirty) await save();
                  onConfirmed(await api.confirm(project.id));
                })
              }
            >
              <Sparkles size={15} />
              {busy === "confirm" ? "Memproses…" : `Konfirmasi & Generate (${generateCount} Gambar)`}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
