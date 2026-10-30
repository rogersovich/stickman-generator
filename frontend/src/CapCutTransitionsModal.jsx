import { Dialog, DialogBackdrop, DialogPanel, DialogTitle } from "@headlessui/react";
import {
  Check,
  CheckSquare,
  Clock,
  Layers,
  RotateCcw,
  Shuffle,
  Square,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "./api.js";

const DEFAULT_TRANSITIONS = [
  { id: "anime_speed", name: "Anime Speed", is_overlap: true },
  { id: "spread_morph", name: "Spread Morph", is_overlap: true },
  { id: "push_away", name: "Push Away", is_overlap: true },
  { id: "pop_switch", name: "Pop Switch", is_overlap: true },
  { id: "stretch_down", name: "Stretch Down", is_overlap: true },
  { id: "left", name: "Left", is_overlap: false },
  { id: "stretch_left", name: "Stretch Left", is_overlap: true },
  { id: "right", name: "Right", is_overlap: false },
  { id: "push_up", name: "Push Up", is_overlap: true },
  { id: "pull_in", name: "Pull In", is_overlap: false },
  { id: "pull_out", name: "Pull Out", is_overlap: false },
  { id: "shake_away", name: "Shake Away", is_overlap: true },
  { id: "shake", name: "Shake", is_overlap: true },
];

const PRESET_DURATIONS = [
  { val: 0.25, label: "0.25s (Cepat)" },
  { val: 0.35, label: "0.35s" },
  { val: 0.50, label: "0.50s (Default)" },
  { val: 0.70, label: "0.70s" },
  { val: 1.00, label: "1.00s (Maksimal)" },
];

export default function CapCutTransitionsModal({
  open,
  onClose,
  selectedTransitions = [],
  onChangeTransitions,
  duration = 0.5,
  onChangeDuration,
}) {
  const [transitions, setTransitions] = useState(DEFAULT_TRANSITIONS);

  useEffect(() => {
    let ignore = false;
    async function load() {
      try {
        const res = await api.capcutTransitions();
        if (!ignore && res?.transitions?.length > 0) {
          setTransitions(res.transitions);
        }
      } catch (e) {
        // Fallback to DEFAULT_TRANSITIONS is already active
      }
    }
    load();
    return () => {
      ignore = true;
    };
  }, []);

  const isChecked = (name) => selectedTransitions.includes(name);

  function toggleTransition(name) {
    if (selectedTransitions.includes(name)) {
      if (selectedTransitions.length > 1) {
        onChangeTransitions?.(selectedTransitions.filter((n) => n !== name));
      }
    } else {
      onChangeTransitions?.([...selectedTransitions, name]);
    }
  }

  function handleSelectAll() {
    onChangeTransitions?.(transitions.map((t) => t.name));
  }

  function handleDeselectAll() {
    const first = transitions[0]?.name || "Anime Speed";
    onChangeTransitions?.([first]);
  }

  function handleReset() {
    onChangeTransitions?.(transitions.map((t) => t.name));
    onChangeDuration?.(0.5);
  }

  return (
    <Dialog open={open} onClose={onClose} className="relative z-60">
      <DialogBackdrop transition className="fixed inset-0 bg-black/80 backdrop-blur-xs duration-150 data-closed:opacity-0" />
      <div className="fixed inset-0 flex items-center justify-center p-4">
        <DialogPanel
          transition
          className="flex max-h-[92vh] w-full max-w-3xl flex-col gap-4 rounded-2xl border border-[#292e3b] bg-[#161920] p-6 shadow-2xl duration-150 data-closed:scale-95 data-closed:opacity-0"
        >
          {/* Header */}
          <div className="flex items-start justify-between gap-3 border-b border-[#292e3b] pb-3">
            <div>
              <DialogTitle className="text-base font-bold text-slate-100">
                Pengaturan Transisi Antar Panel CapCut
              </DialogTitle>
              <p className="mt-0.5 text-xs text-slate-400">
                Konfigurasi transisi video acak dan durasi animasi di timeline CapCut Desktop.
              </p>
            </div>
            <button
              className="rounded-lg p-1.5 text-slate-400 hover:bg-[#1e222b] hover:text-slate-200 transition"
              onClick={onClose}
              aria-label="Tutup"
            >
              <X size={18} />
            </button>
          </div>

          {/* Body */}
          <div className="space-y-4 overflow-y-auto pr-0.5">
            {/* Box Konsep Pengacakan */}
            <div className="rounded-xl border border-teal-500/25 bg-teal-500/5 p-3.5 flex items-start gap-3">
              <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-teal-500/15 text-teal-400 border border-teal-500/30">
                <Shuffle size={18} />
              </div>
              <div className="space-y-0.5 min-w-0 flex-1">
                <h4 className="text-xs font-semibold text-slate-100">
                  Konsep Pengacakan Transisi CapCut
                </h4>
                <p className="text-[12px] text-slate-400 leading-relaxed">
                  Sistem akan memilih secara acak satu transisi dari daftar yang Anda centang di bawah ini untuk setiap batas sambungan antar panel gambar di timeline CapCut Desktop.
                </p>
              </div>
            </div>

            {/* Slider Durasi Transisi */}
            <div className="rounded-xl border border-[#292e3b] bg-[#12141a] p-4 space-y-3.5">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <Clock size={16} className="text-teal-400" />
                  <span className="text-xs font-semibold text-slate-200">Durasi Transisi per Panel</span>
                </div>
                <div className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-teal-500/15 text-teal-300 border border-teal-500/30">
                  <span className="font-mono text-xs font-bold">{duration.toFixed(2)}s</span>
                  <span className="text-[10px] text-slate-400">detik</span>
                </div>
              </div>

              <div className="space-y-2">
                <input
                  type="range"
                  min="0.10"
                  max="1.00"
                  step="0.05"
                  value={duration}
                  onChange={(e) => onChangeDuration?.(parseFloat(e.target.value) || 0.5)}
                  className="w-full accent-teal-400 cursor-pointer h-1.5 bg-[#292e3b] rounded-lg appearance-none"
                />
                <div className="flex justify-between text-[11px] font-mono text-slate-400">
                  <span>0.10s (Minimal)</span>
                  <span className="text-teal-400 font-semibold">0.50s (Rekomendasi)</span>
                  <span>1.00s (Maksimal)</span>
                </div>
              </div>

              {/* Preset Cepat */}
              <div className="flex items-center gap-1.5 pt-1 border-t border-[#292e3b]/60 flex-wrap">
                <span className="text-[11px] text-slate-400 mr-1">Preset Cepat:</span>
                {PRESET_DURATIONS.map((p) => {
                  const isActive = Math.abs((duration ?? 0.5) - p.val) < 0.01;
                  return (
                    <button
                      key={p.val}
                      type="button"
                      className={`px-2.5 py-1 rounded-md text-[11px] font-mono transition border cursor-pointer ${
                        isActive
                          ? "border-teal-500 bg-teal-500/20 text-teal-300 font-bold shadow-xs"
                          : "border-[#292e3b] text-slate-400 hover:text-slate-200 hover:bg-[#181c24]"
                      }`}
                      onClick={() => onChangeDuration?.(p.val)}
                    >
                      {p.label}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Daftar Transisi CapCut */}
            <div className="space-y-3">
              {/* Action Toolbar */}
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <div className="flex items-center gap-2">
                  <Layers size={16} className="text-teal-400" />
                  <span className="text-xs font-semibold text-slate-200">Pilih Transisi Favorit</span>
                  <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-teal-500/15 text-teal-300 border border-teal-500/30 font-mono">
                    {selectedTransitions.length} dari {transitions.length} Aktif
                  </span>
                </div>

                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    onClick={handleSelectAll}
                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-medium border border-[#292e3b] bg-[#12141a] text-slate-200 hover:bg-[#181c24] hover:border-teal-500/50 transition cursor-pointer"
                  >
                    <CheckSquare size={13} className="text-teal-400" />
                    <span>Pilih Semua</span>
                  </button>
                  <button
                    type="button"
                    onClick={handleDeselectAll}
                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-medium border border-[#292e3b] bg-[#12141a] text-slate-200 hover:bg-[#181c24] transition cursor-pointer"
                  >
                    <Square size={13} className="text-slate-400" />
                    <span>Batalkan Semua</span>
                  </button>
                  <button
                    type="button"
                    onClick={handleReset}
                    title="Reset ke pilihan default"
                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-medium border border-[#292e3b] bg-[#12141a] text-slate-400 hover:text-slate-200 hover:bg-[#181c24] transition cursor-pointer"
                  >
                    <RotateCcw size={13} />
                    <span>Reset</span>
                  </button>
                </div>
              </div>

              {/* Grid Transisi */}
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2.5 max-h-[340px] overflow-y-auto pr-1">
                {transitions.map((t) => {
                  const active = isChecked(t.name);
                  return (
                    <div
                      key={t.name}
                      onClick={() => toggleTransition(t.name)}
                      className={`group relative flex items-center justify-between gap-3 p-3 rounded-xl border transition cursor-pointer select-none ${
                        active
                          ? "border-teal-500/60 bg-teal-500/10 ring-1 ring-teal-500/30 shadow-xs"
                          : "border-[#292e3b] bg-[#12141a] hover:bg-[#181c24] opacity-75 hover:opacity-100"
                      }`}
                    >
                      <div className="flex items-center gap-2.5 min-w-0 flex-1">
                        {/* Custom Checkbox */}
                        <div
                          className={`flex size-4.5 shrink-0 items-center justify-center rounded-md border transition ${
                            active
                              ? "border-teal-500 bg-teal-500 text-slate-950"
                              : "border-[#3e4556] bg-[#181c24] group-hover:border-teal-500/60"
                          }`}
                        >
                          {active && <Check size={12} className="stroke-[3]" />}
                        </div>

                        {/* Nama Transisi */}
                        <div className="min-w-0 flex-1">
                          <span
                            className={`block text-xs truncate transition ${
                              active ? "text-slate-100 font-bold" : "text-slate-300 group-hover:text-slate-100 font-medium"
                            }`}
                          >
                            {{ ...t }.name}
                          </span>
                          <span className="text-[10px] text-slate-500 block truncate mt-0.5">
                            {t.is_overlap ? "Overlap Blending" : "Cut-through"}
                          </span>
                        </div>
                      </div>

                      {/* Badge Status */}
                      <div className="shrink-0">
                        <span
                          className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${
                            active
                              ? "bg-teal-500/20 text-teal-300 border-teal-500/30"
                              : "bg-[#181c24] text-slate-500 border-[#292e3b]"
                          }`}
                        >
                          {active ? "Aktif" : "Off"}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Footer */}
          <div className="flex items-center justify-between border-t border-[#292e3b] pt-3">
            <span className="text-xs text-slate-400">
              {selectedTransitions.length} transisi dipilih • durasi {duration.toFixed(2)}s
            </span>
            <button
              type="button"
              onClick={onClose}
              className="flex items-center gap-1.5 rounded-xl bg-teal-500 px-4 py-2 text-xs font-bold text-slate-950 hover:bg-teal-400 transition shadow-lg shadow-teal-500/20 cursor-pointer"
            >
              <Check size={14} className="stroke-[2.5]" />
              <span>Tutup &amp; Simpan</span>
            </button>
          </div>
        </DialogPanel>
      </div>
    </Dialog>
  );
}
