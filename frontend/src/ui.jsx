// Shared form controls and dialogs built on Headless UI conforming to DESIGN.md.
import {
  Description,
  Dialog,
  DialogBackdrop,
  DialogPanel,
  DialogTitle,
  Listbox,
  ListboxButton,
  ListboxOption,
  ListboxOptions,
  Radio,
  RadioGroup,
  Switch,
} from "@headlessui/react";
import { AlertTriangle, Check, CheckCircle2, ChevronsUpDown, Info } from "lucide-react";
import { createContext, useCallback, useContext, useRef, useState } from "react";

// options: [{ value, label, desc? }] or plain strings
const normalize = (options) => options.map((o) => (typeof o === "string" ? { value: o, label: o } : o));

export function Select({ value, onChange, options, className = "", placeholder = "Pilih…" }) {
  const items = normalize(options);
  const selected = items.find((o) => o.value === value);
  return (
    <Listbox value={value} onChange={onChange}>
      <ListboxButton
        className={`input flex items-center justify-between gap-2 text-left data-open:border-amber-500 data-open:ring-1 data-open:ring-amber-500/30 ${className}`}
      >
        <span className={`truncate ${selected ? "text-slate-100 font-medium" : "text-slate-500"}`}>{selected?.label ?? placeholder}</span>
        <ChevronsUpDown size={15} className="shrink-0 text-slate-400" />
      </ListboxButton>
      <ListboxOptions
        anchor="bottom start"
        transition
        className="z-50 w-(--button-width) rounded-xl border border-[#292e3b] bg-[#161920] p-1.5 shadow-2xl [--anchor-gap:4px] [--anchor-max-height:18rem] focus:outline-none data-closed:opacity-0 data-leave:transition data-leave:duration-100"
      >
        {items.map((o) => (
          <ListboxOption
            key={o.value}
            value={o.value}
            className="group flex cursor-pointer items-start gap-2.5 rounded-lg px-2.5 py-2 text-sm select-none text-slate-200 transition-colors data-focus:bg-[#1e222b] data-focus:text-white"
          >
            <Check size={16} className="mt-0.5 shrink-0 text-amber-400 invisible group-data-selected:visible" />
            <div className="min-w-0">
              <div className="group-data-selected:font-semibold group-data-selected:text-amber-200">{o.label}</div>
              {o.desc && <div className="text-xs text-slate-400 mt-0.5">{o.desc}</div>}
            </div>
          </ListboxOption>
        ))}
      </ListboxOptions>
    </Listbox>
  );
}

export function Toggle({ checked, onChange, label, desc }) {
  return (
    <div className="flex items-start gap-3">
      <Switch
        checked={checked}
        onChange={onChange}
        className="group relative mt-0.5 inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full bg-[#292e3b] transition duration-150 data-checked:bg-amber-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/50"
      >
        <span className="pointer-events-none inline-block size-5 translate-x-0.5 translate-y-0.5 rounded-full bg-slate-100 shadow-sm transition group-data-checked:translate-x-5.5" />
      </Switch>
      <div className="text-sm">
        <div className="font-medium text-slate-200">{label}</div>
        {desc && <div className="text-xs text-slate-400 mt-0.5 leading-relaxed">{desc}</div>}
      </div>
    </div>
  );
}

// Card-style single choice (format picker, tempo presets)
export function ChoiceCards({ value, onChange, options, className = "" }) {
  return (
    <RadioGroup value={value} onChange={onChange} className={`grid gap-2.5 ${className}`}>
      {normalize(options).map((o) => (
        <Radio
          key={o.value}
          value={o.value}
          disabled={o.disabled}
          className="cursor-pointer rounded-xl border border-[#292e3b] bg-[#161920] px-3.5 py-3 text-left text-sm transition focus-visible:outline-none data-checked:border-amber-500/80 data-checked:bg-amber-500/10 data-checked:text-amber-100 data-disabled:cursor-default data-disabled:border-[#20242e] data-disabled:opacity-40 data-focus-visible:ring-2 data-focus-visible:ring-amber-500/40 hover:border-[#3d4455]"
        >
          <div className="font-semibold text-slate-100 data-checked:text-amber-300">{o.label}</div>
          {o.desc && <div className="text-xs text-slate-400 mt-1 leading-normal">{o.desc}</div>}
        </Radio>
      ))}
    </RadioGroup>
  );
}

// ---------- confirm / alert modal ----------
const DialogContext = createContext(null);

export function DialogProvider({ children }) {
  const [state, setState] = useState(null); // { kind, title, message, confirmLabel, cancelLabel, danger }
  const resolver = useRef(null);

  const open = useCallback(
    (kind, opts) =>
      new Promise((resolve) => {
        resolver.current = resolve;
        setState({ kind, ...opts });
      }),
    []
  );

  const close = (result) => {
    resolver.current?.(result);
    resolver.current = null;
    setState((s) => (s ? { ...s, closing: true } : s));
  };

  const api = useRef({
    confirm: (opts) => open("confirm", opts),
    alert: (opts) => open("alert", opts),
    success: (opts) => open("alert", { tone: "success", ...opts }),
  }).current;

  const danger = state?.danger;
  const tone = state?.tone ?? (danger ? "error" : state?.kind === "alert" ? "warning" : "info");
  const Icon = tone === "success" ? CheckCircle2 : tone === "error" || tone === "warning" ? AlertTriangle : Info;
  const toneClasses =
    tone === "success"
      ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400"
      : tone === "error"
      ? "border-red-500/30 bg-red-500/10 text-red-400"
      : tone === "warning"
      ? "border-amber-500/30 bg-amber-500/10 text-amber-400"
      : "border-sky-500/30 bg-sky-500/10 text-sky-400";

  return (
    <DialogContext.Provider value={api}>
      {children}
      <Dialog
        open={!!state && !state.closing}
        onClose={() => close(false)}
        transition
        className="relative z-[60]"
      >
        <DialogBackdrop transition className="fixed inset-0 bg-black/80 backdrop-blur-xs duration-150 ease-out data-closed:opacity-0" />
        <div className="fixed inset-0 flex items-center justify-center p-4">
          <DialogPanel
            transition
            className="w-full max-w-md space-y-4 rounded-2xl border border-[#292e3b] bg-[#161920] p-6 shadow-2xl duration-150 ease-out data-closed:scale-95 data-closed:opacity-0"
          >
            <div className="flex gap-3.5">
              <div
                className={`flex size-10 shrink-0 items-center justify-center rounded-xl border ${toneClasses}`}
              >
                <Icon size={20} />
              </div>
              <div className="min-w-0 space-y-1.5">
                <DialogTitle className="text-base font-bold tracking-tight text-slate-100">{state?.title}</DialogTitle>
                {state?.message && (
                  <Description className="text-sm leading-relaxed whitespace-pre-line break-words text-slate-300">{state.message}</Description>
                )}
              </div>
            </div>
            <div className="flex justify-end gap-2.5 pt-2">
              {state?.kind === "confirm" && (
                <button className="btn-ghost px-4 py-2 text-sm" onClick={() => close(false)}>
                  {state?.cancelLabel ?? "Batal"}
                </button>
              )}
              <button
                autoFocus
                className={danger ? "btn bg-red-600 text-white hover:bg-red-500 px-4 py-2" : "btn-primary px-4 py-2"}
                onClick={() => close(true)}
              >
                {state?.confirmLabel ?? (state?.kind === "alert" ? "OK" : "Ya, lanjut")}
              </button>
            </div>
          </DialogPanel>
        </div>
      </Dialog>
    </DialogContext.Provider>
  );
}

export function useDialog() {
  const ctx = useContext(DialogContext);
  if (!ctx) throw new Error("useDialog must be used inside <DialogProvider>");
  return ctx;
}
