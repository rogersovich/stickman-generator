import { Dialog, DialogBackdrop, DialogPanel, DialogTitle, Radio, RadioGroup } from "@headlessui/react";
import { BookOpen, Check, Loader2, Maximize2, Minimize2, RefreshCw, Shuffle, Sparkles, WandSparkles, X } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "./api.js";

const MODES = [
  { value: "shorter", label: "Lebih Ringkas", icon: Minimize2 },
  { value: "longer", label: "Lebih Detail", icon: Maximize2 },
  { value: "simpler", label: "Bahasa Santai", icon: BookOpen },
  { value: "reword", label: "Variasi Kata", icon: Shuffle },
];

const wordCount = (t) => t.split(/\s+/).filter(Boolean).length;
const seconds = (t) => Math.round(wordCount(t) / 2.5);

// Modal: ask the AI for 3 alternative narrations of one scene and pick one.
export default function NarrationEditor({ open, onClose, projectId, index, current, onApply }) {
  const [mode, setMode] = useState(null);
  const [instruction, setInstruction] = useState("");
  const [options, setOptions] = useState([]);
  const [choice, setChoice] = useState(null);
  const [model, setModel] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    setMode(null);
    setInstruction("");
    setOptions([]);
    setChoice(null);
    setError("");
  }, [open, index]);

  async function generate(nextMode = mode) {
    if (!nextMode && !instruction.trim()) return;
    setMode(nextMode);
    setLoading(true);
    setError("");
    setOptions([]);
    setChoice(null);
    try {
      const r = await api.narrationOptions(projectId, index, { mode: nextMode, instruction });
      setOptions(r.options);
      setModel(r.model);
      setChoice(r.options[0] ?? null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function apply() {
    setSaving(true);
    try {
      await onApply(choice);
      onClose();
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onClose={() => !loading && !saving && onClose()} className="relative z-[55]">
      <DialogBackdrop transition className="fixed inset-0 bg-black/80 backdrop-blur-xs duration-150 data-closed:opacity-0" />
      <div className="fixed inset-0 overflow-y-auto p-4">
        <div className="flex min-h-full items-center justify-center">
          <DialogPanel
            transition
            className="w-full max-w-2xl space-y-5 rounded-2xl border border-[#292e3b] bg-[#161920] p-6 shadow-2xl duration-150 data-closed:scale-95 data-closed:opacity-0"
          >
            <div className="flex items-start justify-between gap-3 border-b border-[#292e3b] pb-3">
              <DialogTitle className="flex items-center gap-2.5 text-base font-bold text-slate-100">
                <div className="flex size-7 items-center justify-center rounded-lg border border-amber-500/30 bg-amber-500/10 text-amber-400">
                  <WandSparkles size={15} />
                </div>
                Poles Narasi Adegan #{index + 1}
              </DialogTitle>
              <button
                className="rounded-lg p-1 text-slate-400 hover:bg-[#1e222b] hover:text-white transition-colors"
                onClick={onClose}
                aria-label="Tutup"
                disabled={loading || saving}
              >
                <X size={18} />
              </button>
            </div>

            <div className="rounded-xl border border-[#292e3b] bg-[#12141a] p-3.5 space-y-1">
              <div className="flex items-center justify-between text-xs font-mono text-slate-400">
                <span className="uppercase tracking-wider">Narasi Saat Ini</span>
                <span>{wordCount(current)} kata · ±{seconds(current)}s</span>
              </div>
              <p className="text-sm leading-relaxed text-slate-200">{current}</p>
            </div>

            <div className="space-y-3">
              <p className="label">Mode Penyesuaian Cepat</p>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {MODES.map(({ value, label, icon: Icon }) => (
                  <button
                    key={value}
                    disabled={loading}
                    onClick={() => generate(value)}
                    className={`btn border text-xs py-2 ${
                      mode === value
                        ? "border-amber-500/80 bg-amber-500/10 text-amber-300 font-semibold"
                        : "border-[#292e3b] bg-[#1e222b] text-slate-300 hover:border-[#3d4455] hover:bg-[#252b36]"
                    }`}
                  >
                    <Icon size={14} className={mode === value ? "text-amber-400" : "text-slate-400"} />
                    {label}
                  </button>
                ))}
              </div>

              <div className="flex gap-2">
                <input
                  className="input"
                  placeholder="Instruksi khusus (opsional), misal: buat lebih dramatis dan ajak penonton berkomentar"
                  value={instruction}
                  onChange={(e) => setInstruction(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && generate()}
                  disabled={loading}
                />
                <button
                  className="btn-ghost shrink-0 px-3.5"
                  disabled={loading || (!mode && !instruction.trim())}
                  onClick={() => generate()}
                >
                  <Sparkles size={15} className="text-amber-400" />
                  <span>Generate</span>
                </button>
              </div>
              <p className="text-xs text-slate-400">
                AI mempertimbangkan kesinambungan naskah adegan sebelum & sesudahnya agar nada cerita tetap konsisten.
              </p>
            </div>

            {loading && (
              <div className="flex items-center gap-3 rounded-xl border border-[#292e3b] bg-[#12141a] p-4 text-sm text-slate-300 font-mono">
                <Loader2 size={16} className="animate-spin text-amber-400" />
                <span>AI sedang menyusun 3 alternatif narasi…</span>
              </div>
            )}

            {error && (
              <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-3.5 text-sm text-red-300">
                {error}
              </div>
            )}

            {options.length > 0 && (
              <div className="space-y-2.5">
                <div className="flex items-center justify-between">
                  <p className="label mb-0">Pilih Alternatif Terbaik</p>
                  <span className="font-mono text-xs text-slate-400">{model}</span>
                </div>
                <RadioGroup value={choice} onChange={setChoice} className="space-y-2">
                  {options.map((text, i) => (
                    <Radio
                      key={i}
                      value={text}
                      className="group flex cursor-pointer gap-3.5 rounded-xl border border-[#292e3b] bg-[#1e222b] p-3.5 transition focus-visible:outline-none data-checked:border-amber-500/80 data-checked:bg-amber-500/10 data-focus-visible:ring-2 data-focus-visible:ring-amber-500/40 hover:border-[#3d4455]"
                    >
                      <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border border-slate-600 group-data-checked:border-amber-500 group-data-checked:bg-amber-500">
                        <Check size={12} className="invisible text-slate-950 group-data-checked:visible" />
                      </span>
                      <div className="space-y-1">
                        <p className="text-sm leading-relaxed text-slate-100">{text}</p>
                        <p className="font-mono text-xs text-slate-400">
                          Opsi {i + 1} · {wordCount(text)} kata · ±{seconds(text)}s
                        </p>
                      </div>
                    </Radio>
                  ))}
                </RadioGroup>
              </div>
            )}

            <div className="flex flex-wrap items-center justify-end gap-2.5 pt-2 border-t border-[#292e3b]">
              {options.length > 0 && (
                <button
                  className="btn-ghost mr-auto text-xs"
                  disabled={loading || saving}
                  onClick={() => generate()}
                >
                  <RefreshCw size={14} /> Generate Ulang
                </button>
              )}
              <button className="btn-ghost" onClick={onClose} disabled={loading || saving}>
                Batal
              </button>
              <button className="btn-primary" disabled={!choice || loading || saving} onClick={apply}>
                <Check size={16} /> {saving ? "Menerapkan…" : "Gunakan Narasi Ini"}
              </button>
            </div>
          </DialogPanel>
        </div>
      </div>
    </Dialog>
  );
}
