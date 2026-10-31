import { useEffect, useRef, useState } from "react";
import { Clapperboard, Film, Loader2, Trash2, UploadCloud } from "lucide-react";
import { api } from "./api.js";
import { go } from "./App.jsx";
import { confirmDelete } from "./deleteProject.js";
import { ChoiceCards, useDialog } from "./ui.jsx";

const STATUS_LABEL = {
  draft: "Draft",
  generating: "Generating",
  paused: "Paused",
  done: "Selesai",
};

const STATUS_BADGE = {
  draft: "bg-slate-800 text-slate-300 border-slate-700",
  generating: "bg-amber-500/15 text-amber-300 border-amber-500/40 animate-pulse",
  paused: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  done: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
};

export default function Home() {
  const dialog = useDialog();
  const fileInputRef = useRef(null);

  // Import state
  const [markdownText, setMarkdownText] = useState("");
  const [parsedPreview, setParsedPreview] = useState(null);
  const [importTitle, setImportTitle] = useState("");
  const [importFormat, setImportFormat] = useState("16:9");
  const [autoConfirm, setAutoConfirm] = useState(false);
  const [parsing, setParsing] = useState(false);
  const [importLoading, setImportLoading] = useState(false);
  const [importError, setImportError] = useState("");
  const [uploadedFileName, setUploadedFileName] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const dragCounter = useRef(0);
  const [projects, setProjects] = useState([]);
  const [loadingProjects, setLoadingProjects] = useState(true);

  useEffect(() => {
    setLoadingProjects(true);
    api
      .projects()
      .then(setProjects)
      .catch(() => {})
      .finally(() => setLoadingProjects(false));
  }, []);

  // When markdownText changes, run parse preview
  async function handleMarkdownChange(text) {
    setMarkdownText(text);
    setImportError("");
    if (!text.trim()) {
      setParsedPreview(null);
      return;
    }
    setParsing(true);
    try {
      const res = await api.parseMarkdownPreview(text);
      setParsedPreview(res);
      setImportTitle(res.title);
      setImportFormat(res.format);
    } catch (err) {
      setImportError(err.message);
      setParsedPreview(null);
    } finally {
      setParsing(false);
    }
  }

  // Handle file reading from input or drag-and-drop
  function handleFile(file) {
    if (!file) return;
    setUploadedFileName(file.name);
    const reader = new FileReader();
    reader.onload = (event) => {
      const content = event.target?.result;
      if (typeof content === "string") {
        handleMarkdownChange(content);
      }
    };
    reader.readAsText(file);
  }

  function handleFileUpload(e) {
    const file = e.target.files?.[0];
    if (file) {
      handleFile(file);
    }
    // reset input so selecting the same file again triggers onChange
    if (e.target) {
      e.target.value = "";
    }
  }

  function handleDragEnter(e) {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current += 1;
    if (e.dataTransfer?.items && e.dataTransfer.items.length > 0) {
      setIsDragging(true);
    }
  }

  function handleDragOver(e) {
    e.preventDefault();
    e.stopPropagation();
    if (e.dataTransfer) {
      e.dataTransfer.dropEffect = "copy";
    }
    setIsDragging(true);
  }

  function handleDragLeave(e) {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current -= 1;
    if (dragCounter.current <= 0) {
      dragCounter.current = 0;
      setIsDragging(false);
    }
  }

  function handleDrop(e) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    dragCounter.current = 0;
    const file = e.dataTransfer?.files?.[0];
    if (file) {
      handleFile(file);
    }
  }

  async function submitImport(e) {
    e.preventDefault();
    if (!markdownText.trim()) return;
    setImportLoading(true);
    setImportError("");
    try {
      const p = await api.importMarkdown({
        markdown: markdownText,
        title: importTitle || parsedPreview?.title,
        format: importFormat,
        auto_confirm: autoConfirm,
      });
      go(`/project/${p.id}`);
    } catch (err) {
      setImportError(err.message);
    } finally {
      setImportLoading(false);
    }
  }

  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_340px]">
      {/* Main Studio Workbench */}
      <div className="space-y-5">
          <form
            onSubmit={submitImport}
            onDragOver={(e) => e.preventDefault()}
            className="panel p-6 space-y-5"
          >
            <div>
              <h2 className="text-lg font-bold tracking-tight text-slate-100">Import Prompt per Adegan</h2>
              <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                Kirim dokumen Markdown (seperti <code className="font-mono text-amber-300">prompts.md</code>) yang berisi daftar adegan, naskah narasi di tiap <code className="font-mono text-amber-300">Beat narasi:</code>, dan prompt Google Flow.
              </p>
            </div>

            {/* Dropzone / Upload button */}
            <div
              onClick={() => fileInputRef.current?.click()}
              onDragEnter={handleDragEnter}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              className={`group cursor-pointer rounded-xl border-2 border-dashed p-6 text-center transition-all duration-150 ${
                isDragging
                  ? "border-amber-400 bg-amber-500/15 ring-4 ring-amber-500/20 scale-[1.01]"
                  : "border-[#292e3b] bg-[#12141a] hover:border-amber-500/60 hover:bg-[#151821]"
              }`}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".md,.txt,.markdown"
                className="hidden"
                onChange={handleFileUpload}
              />
              <div className="pointer-events-none mx-auto flex size-12 items-center justify-center rounded-xl border border-[#292e3b] bg-[#1e222b] text-amber-400 transition-transform group-hover:border-amber-400 group-hover:bg-amber-500/10">
                <UploadCloud size={24} className={isDragging ? "animate-bounce text-amber-300" : ""} />
              </div>
              <div className="pointer-events-none mt-3 text-sm font-semibold text-slate-200 group-hover:text-amber-300">
                {isDragging ? (
                  <span className="text-amber-300 font-bold">Lepaskan file .md di sini sekarang!</span>
                ) : uploadedFileName ? (
                  <span className="text-amber-300">
                    File aktif: <span className="font-mono underline underline-offset-2">{uploadedFileName}</span> (Klik atau drop file lain)
                  </span>
                ) : (
                  <>
                    Klik untuk pilih file <span className="font-mono">.md</span> atau drag & drop ke sini
                  </>
                )}
              </div>
              <div className="pointer-events-none mt-1 text-xs text-slate-500">
                Mendukung format naskah berscene lengkap dengan beat narasi & kode prompt
              </div>
            </div>

            {/* Textarea for Direct Paste */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="label mb-0">Atau Tempel / Paste Konten Markdown di Sini</label>
                {(markdownText.length > 0 || uploadedFileName) && (
                  <button
                    type="button"
                    onClick={() => {
                      handleMarkdownChange("");
                      setUploadedFileName("");
                    }}
                    className="text-xs text-slate-500 hover:text-slate-300"
                  >
                    Kosongkan
                  </button>
                )}
              </div>
              <textarea
                className="input min-h-36 font-mono text-xs leading-relaxed resize-y"
                placeholder="# Judul Cerita...&#10;&#10;## Scene 1 - WIDE SHOT&#10;Beat narasi: Kamu guru honorer di pinggir kota...&#10;```&#10;CREATE IMAGE&#10;...&#10;```"
                value={markdownText}
                onChange={(e) => handleMarkdownChange(e.target.value)}
                onDragOver={(e) => {
                  if (e.dataTransfer?.types?.includes("Files")) {
                    e.preventDefault();
                  }
                }}
                onDrop={handleDrop}
              />
            </div>

            {parsing && (
              <div className="flex items-center gap-2 rounded-xl border border-[#292e3b] bg-[#12141a] p-4 text-xs font-mono text-slate-300">
                <Loader2 size={15} className="animate-spin text-amber-400" />
                <span>Membaca dan memetakan struktur adegan...</span>
              </div>
            )}

            {/* Parsed Preview Card */}
            {parsedPreview && (
              <div className="rounded-xl border border-amber-500/40 bg-amber-500/5 p-4.5 space-y-4">
                <div className="flex items-center justify-between border-b border-amber-500/20 pb-3">
                  <div className="flex items-center gap-2">
                    <span className="flex size-2 rounded-full bg-amber-400" />
                    <span className="text-xs font-bold uppercase tracking-wider text-amber-300">
                      Struktur Naskah Terdeteksi
                    </span>
                  </div>
                  <div className="flex items-center gap-2 font-mono text-xs">
                    <span className="rounded border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-amber-300 font-semibold">
                      {parsedPreview.total_scenes} Adegan
                    </span>
                    {parsedPreview.merged_scenes_count > 0 && (
                      <span className="rounded border border-[#292e3b] bg-[#161920] px-2 py-0.5 text-slate-300">
                        {parsedPreview.total_scenes - parsedPreview.merged_scenes_count} gambar + {parsedPreview.merged_scenes_count} gabung
                      </span>
                    )}
                  </div>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="sm:col-span-2">
                    <label className="label text-amber-300/80">Judul Project</label>
                    <input
                      className="input font-bold text-slate-100"
                      value={importTitle}
                      onChange={(e) => setImportTitle(e.target.value)}
                    />
                  </div>

                  <div>
                    <label className="label text-amber-300/80">Format Video</label>
                    <ChoiceCards
                      className="grid-cols-2"
                      value={importFormat}
                      onChange={setImportFormat}
                      options={[
                        { value: "16:9", label: "16:9 Landscape" },
                        { value: "9:16", label: "9:16 Vertikal" },
                      ]}
                    />
                  </div>

                  <div>
                    <label className="label text-amber-300/80">Opsi Langsung</label>
                    <div className="rounded-xl border border-[#292e3b] bg-[#161920] p-3">
                      <label className="flex items-center gap-2.5 cursor-pointer text-xs font-medium text-slate-200">
                        <input
                          type="checkbox"
                          checked={autoConfirm}
                          onChange={(e) => setAutoConfirm(e.target.checked)}
                          className="size-4 rounded accent-amber-500"
                        />
                        <span>Langsung aktifkan antrian generate</span>
                      </label>
                      <p className="text-[11px] text-slate-400 mt-1">
                        Jika dicentang, project langsung siap diproses oleh worker Chrome Extension tanpa konfirmasi ulang.
                      </p>
                    </div>
                  </div>
                </div>

                {/* Sample scenes preview */}
                {parsedPreview.scenes?.length > 0 && (
                  <div className="space-y-1.5 pt-1">
                    <div className="text-[11px] font-mono uppercase tracking-wider text-slate-400">
                      Contoh 2 Adegan Pertama:
                    </div>
                    <div className="space-y-2">
                      {parsedPreview.scenes.slice(0, 2).map((s, idx) => (
                        <div key={idx} className="rounded-lg border border-[#292e3b] bg-[#12141a] p-3 text-xs space-y-1">
                          <div className="flex items-center justify-between font-mono text-[11px] text-amber-400">
                            <span>SCENE {s.scene_num} {s.tag ? `· ${s.tag}` : ""}</span>
                            {s.is_merged && <span className="text-amber-300 font-semibold">[DIGABUNG]</span>}
                          </div>
                          <p className="text-slate-200 font-medium">"{s.narration}"</p>
                          <div className="font-mono text-[10px] text-slate-400 truncate">
                            Prompt: {s.prompt.slice(0, 80)}...
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {importError && (
              <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-3.5 text-sm text-red-300">
                {importError}
              </div>
            )}

            <button
              className="btn-primary w-full py-3 text-sm"
              disabled={importLoading || !markdownText.trim() || !parsedPreview}
            >
              {importLoading ? <Loader2 size={16} className="animate-spin" /> : <Clapperboard size={16} />}
              {importLoading
                ? "Menyiapkan project studio…"
                : `Buat Project (${parsedPreview?.total_scenes ?? 0} Adegan) & Buka Storyboard`}
            </button>
          </form>

      </div>

      {/* Sidebar: Project Reel History */}
      <aside className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-xs font-bold tracking-wider text-slate-400 uppercase">
            <Film size={14} className="text-amber-400" />
            Project Tersimpan
          </h2>
          <span className="font-mono text-xs text-slate-400">
            {loadingProjects ? (
              <span className="inline-flex items-center gap-1 text-slate-400">
                <Loader2 size={12} className="animate-spin text-amber-400" /> memuat…
              </span>
            ) : (
              `${projects.length} reel`
            )}
          </span>
        </div>

        {loadingProjects ? (
          <div className="space-y-2.5 animate-pulse">
            <div className="rounded-xl border border-[#292e3b] bg-[#1e222b]/60 p-4 space-y-2.5">
              <div className="h-4 w-3/4 rounded bg-slate-700/50" />
              <div className="flex gap-2">
                <div className="h-3.5 w-12 rounded bg-slate-800" />
                <div className="h-3.5 w-16 rounded bg-slate-800" />
                <div className="h-3.5 w-20 rounded bg-slate-800" />
              </div>
            </div>
            <div className="rounded-xl border border-[#292e3b] bg-[#1e222b]/40 p-4 space-y-2.5">
              <div className="h-4 w-1/2 rounded bg-slate-700/40" />
              <div className="flex gap-2">
                <div className="h-3.5 w-12 rounded bg-slate-800" />
                <div className="h-3.5 w-16 rounded bg-slate-800" />
              </div>
            </div>
            <div className="flex items-center justify-center gap-2 py-2 text-xs text-slate-400 font-mono">
              <Loader2 size={13} className="animate-spin text-amber-400" />
              <span>Memuat project tersimpan…</span>
            </div>
          </div>
        ) : projects.length === 0 ? (
          <div className="rounded-xl border border-dashed border-[#292e3b] p-6 text-center text-sm text-slate-400">
            Belum ada project tersimpan. Import file markdown prompt di samping untuk memulai.
          </div>
        ) : (
          <ul className="space-y-2.5">
            {projects.map((p) => (
              <li key={p.id} className="group relative">
                <button
                  onClick={() => go(`/project/${p.id}`)}
                  className="card w-full p-3.5 pr-10 text-left transition-all hover:border-[#3d4455] hover:bg-[#232833] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/40"
                >
                  <div className="truncate text-sm font-semibold text-slate-100 group-hover:text-amber-300 transition-colors">
                    {p.title}
                  </div>
                  <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs text-slate-400 font-mono">
                    <span className="rounded border border-[#292e3b] bg-[#161920] px-1.5 py-0.5 text-[11px]">
                      {p.format}
                    </span>
                    <span className={`rounded border px-1.5 py-0.5 text-[11px] ${STATUS_BADGE[p.status] ?? "border-slate-700 bg-slate-800"}`}>
                      {STATUS_LABEL[p.status] ?? p.status}
                    </span>
                    <span className="text-slate-400">
                      {p.done_count}/{p.scene_count} frame
                    </span>
                    {p.low_res_count > 0 && (
                      <span className="rounded bg-amber-500/10 px-1.5 py-0.5 text-[11px] text-amber-300 border border-amber-500/20">
                        {p.low_res_count} low-res
                      </span>
                    )}
                  </div>
                </button>
                <button
                  onClick={async () => {
                    if (await confirmDelete(p, dialog)) setProjects((list) => list.filter((x) => x.id !== p.id));
                  }}
                  className="absolute top-1/2 right-2.5 -translate-y-1/2 rounded-lg p-1.5 text-slate-400 opacity-0 transition group-hover:opacity-100 hover:bg-red-500/15 hover:text-red-300 focus:opacity-100"
                  aria-label={`Hapus project ${p.title}`}
                  title="Hapus project"
                >
                  <Trash2 size={15} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </aside>
    </div>
  );
}
