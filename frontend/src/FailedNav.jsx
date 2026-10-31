import { useState } from "react";
import { AlertTriangle, ChevronDown, ChevronUp } from "lucide-react";

// Jump between failed rows/cards: cursor points into `indexes`, flash highlights the target briefly.
// Targets are looked up by element id `${idPrefix}${index}`.
export function useFailedNav(indexes, idPrefix) {
  const [cursor, setCursor] = useState(-1);
  const [flash, setFlash] = useState(null);

  function goTo(step) {
    const n = indexes.length;
    if (!n) return;
    const current = Math.min(cursor, n - 1);
    const next = current < 0 ? (step > 0 ? 0 : n - 1) : (current + step + n) % n;
    const i = indexes[next];
    setCursor(next);
    document.getElementById(`${idPrefix}${i}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    setFlash(i);
    setTimeout(() => setFlash((f) => (f === i ? null : f)), 1800);
  }

  return { indexes, cursor: Math.min(cursor, indexes.length - 1), flash, goTo };
}

// Floating "Gagal 2/3 · #7 ▲ ▼" pill; hidden when nothing failed.
export default function FailedNav({ nav, noun = "frame" }) {
  const { indexes, cursor, goTo } = nav;
  if (!indexes.length) return null;
  return (
    <div className="fixed bottom-5 left-1/2 z-40 flex -translate-x-1/2 items-center gap-1 whitespace-nowrap rounded-full border border-red-500/40 bg-[#1a1d25]/95 p-1 pl-3 text-xs text-red-300 shadow-lg backdrop-blur">
      <button className="flex items-center gap-1.5 font-mono hover:text-red-200" onClick={() => goTo(cursor < 0 ? 1 : 0)} title={`Lompat ke ${noun} gagal`}>
        <AlertTriangle size={13} />
        Gagal {cursor < 0 ? "–" : cursor + 1}/{indexes.length}
        {cursor >= 0 && <span className="text-red-400/70">· #{indexes[cursor] + 1}</span>}
      </button>
      <button className="ml-1 rounded-full p-1.5 hover:bg-red-500/15" onClick={() => goTo(-1)} title={`${noun} gagal sebelumnya`} aria-label={`${noun} gagal sebelumnya`}>
        <ChevronUp size={15} />
      </button>
      <button className="rounded-full p-1.5 hover:bg-red-500/15" onClick={() => goTo(1)} title={`${noun} gagal berikutnya`} aria-label={`${noun} gagal berikutnya`}>
        <ChevronDown size={15} />
      </button>
    </div>
  );
}
