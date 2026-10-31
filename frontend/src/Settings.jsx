import { useEffect, useRef, useState } from "react";
import { AlertCircle, AudioLines, Check, Clock, Cloud, Copy, Cpu, Database, HardDrive, Info, Layers, Lock, Pause, Play, Save, Sliders, Volume2 } from "lucide-react";
import { api } from "./api.js";
import { ChoiceCards, Select, Toggle } from "./ui.jsx";

// Tempo presets: the pacing fields they set (seconds unless noted).
const PRESETS = {
  santai: {
    label: "Santai",
    desc: "Paling mirip manusia, jeda panjang dan aman",
    values: {
      delay_between_images: { min: 45, max: 120 },
      delay_between_redownloads: { min: 6, max: 15 },
      before_send: { min: 0.8, max: 2.0 },
    },
  },
  normal: {
    label: "Normal",
    desc: "Seimbang dan optimal untuk pengerjaan harian (default)",
    values: {
      delay_between_images: { min: 15, max: 40 },
      delay_between_redownloads: { min: 3, max: 8 },
      before_send: { min: 0.4, max: 1.0 },
    },
  },
  cepat: {
    label: "Cepat (Turbo)",
    desc: "Sangat cepat dengan paste instan, jeda antar gambar minimal",
    values: {
      delay_between_images: { min: 5, max: 15 },
      delay_between_redownloads: { min: 1.5, max: 3 },
      before_send: { min: 0.2, max: 0.5 },
    },
  },
};

function Section({ title, desc, icon: Icon, children }) {
  return (
    <section className="panel p-6 space-y-4">
      <div className="flex items-start gap-3 border-b border-[#292e3b] pb-3">
        {Icon && (
          <div className="flex size-7 items-center justify-center rounded-lg border border-[#292e3b] bg-[#1e222b] text-amber-400 mt-0.5">
            <Icon size={15} />
          </div>
        )}
        <div>
          <h2 className="text-base font-bold text-slate-100">{title}</h2>
          {desc && <p className="text-xs text-slate-400 mt-0.5 leading-relaxed">{desc}</p>}
        </div>
      </div>
      {children}
    </section>
  );
}

function Field({ label, hint, children }) {
  return (
    <div className="space-y-1.5">
      <label className="label mb-0">{label}</label>
      {children}
      {hint && <p className="text-xs text-slate-400 leading-normal">{hint}</p>}
    </div>
  );
}

function RangeInput({ value, onChange, unit, step = 0.1 }) {
  const set = (key) => (e) => onChange({ ...value, [key]: e.target.value === "" ? "" : Number(e.target.value) });
  return (
    <div className="flex items-center gap-2">
      <input className="input font-mono" type="number" min={0} step={step} value={value.min} onChange={set("min")} />
      <span className="text-slate-500 font-mono">–</span>
      <input className="input font-mono" type="number" min={0} step={step} value={value.max} onChange={set("max")} />
      <span className="w-12 shrink-0 font-mono text-xs text-slate-400">{unit}</span>
    </div>
  );
}

function SliderField({ label, hint, value, min, max, step = 1, defaultValue, unit = "", onChange }) {
  const current = value ?? defaultValue;
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <label className="label mb-0">{label}</label>
        <span className="font-mono text-xs text-amber-300">
          {current}{unit ? ` ${unit}` : ""} <span className="text-slate-500 font-normal">(default: {defaultValue}{unit ? ` ${unit}` : ""})</span>
        </span>
      </div>
      <div className="flex items-center gap-3">
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={current}
          onChange={(e) => onChange(Number(e.target.value))}
          className="flex-1 accent-amber-500 cursor-pointer"
        />
        <input
          type="number"
          min={min}
          max={max}
          step={step}
          value={current}
          onChange={(e) => onChange(Number(e.target.value))}
          className="input font-mono text-xs w-20 text-right"
        />
      </div>
      {hint && <p className="text-xs text-slate-400 leading-normal">{hint}</p>}
    </div>
  );
}

export default function Settings() {
  const [settings, setSettings] = useState(null);
  const [models, setModels] = useState([]);
  const [styles, setStyles] = useState([]);
  const [voices, setVoices] = useState([]);
  const [storageStatus, setStorageStatus] = useState(null);
  const [copiedRclone, setCopiedRclone] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);
  const [playingVoiceId, setPlayingVoiceId] = useState(null);
  const voiceAudioRef = useRef(null);

  function stopVoiceAudio() {
    if (voiceAudioRef.current) {
      voiceAudioRef.current.pause();
      voiceAudioRef.current = null;
    }
    setPlayingVoiceId(null);
  }

  function toggleVoicePlay(id) {
    if (voiceAudioRef.current) {
      voiceAudioRef.current.pause();
      voiceAudioRef.current = null;
    }
    if (playingVoiceId === id) {
      setPlayingVoiceId(null);
      return;
    }
    if (!id) return;
    const a = new Audio(api.voiceAudioUrl(id));
    voiceAudioRef.current = a;
    setPlayingVoiceId(id);
    a.play().catch(() => {
      setPlayingVoiceId(null);
      voiceAudioRef.current = null;
    });
    a.onended = () => {
      setPlayingVoiceId(null);
      voiceAudioRef.current = null;
    };
    a.onerror = () => {
      setPlayingVoiceId(null);
      voiceAudioRef.current = null;
    };
  }

  useEffect(() => {
    return () => stopVoiceAudio();
  }, []);

  useEffect(() => {
    api.settings().then(setSettings).catch((e) => setMessage({ error: true, text: e.message }));
    api.config().then((c) => setModels(c.models)).catch(() => {});
    api.styles().then(setStyles).catch(() => {});
    api.voices().then(setVoices).catch(() => {});
    api.storageStatus().then(setStorageStatus).catch(() => {});
  }, []);

  if (!settings) return <p className="p-8 text-center font-mono text-sm text-slate-400">{message?.text ?? "Memuat konfigurasi studio…"}</p>;

  const update = (patch) => {
    setSettings((s) => ({ ...s, ...patch }));
    setDirty(true);
    setMessage(null);
  };
  const pacing = (key) => (value) => update({ [key]: value, tempo_preset: "custom" });
  const field = (key, cast = (v) => v) => (e) => update({ [key]: cast(e.target.value) });

  async function save() {
    setSaving(true);
    try {
      setSettings(await api.saveSettings(settings));
      setDirty(false);
      setMessage({ text: "Pengaturan berhasil disimpan. Worker akan menggunakan setelan baru mulai job berikutnya." });
    } catch (e) {
      setMessage({ error: true, text: e.message });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6 pb-28">
      <div>
        <h1 className="text-xl font-bold tracking-tight text-slate-100">Pengaturan Studio</h1>
        <p className="text-xs text-slate-400 mt-1">
          Sesuaikan preferensi model, tempo pengetikan worker Google Flow, dan pembatasan sesi kerja.
        </p>
      </div>

      <Section title="Konfigurasi Naskah & Cerita" desc="Nilai default saat Anda membuka form Cerita Baru dan parameter LLM 9router." icon={Cpu}>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Model Pembuat Cerita Default" hint="Model LLM utama yang dipakai di 9router.">
            <Select value={settings.default_model} onChange={(v) => update({ default_model: v })} options={models} />
          </Field>
          <Field label="Model Poles Narasi AI" hint="Digunakan pada tombol 'Edit dengan AI' di editor.">
            <Select value={settings.rewrite_model} onChange={(v) => update({ rewrite_model: v })} options={models} />
          </Field>
          <Field label="Target Detik per Adegan" hint="Mempengaruhi estimasi durasi dan jumlah adegan (±2,5 kata/detik).">
            <div className="relative">
              <input
                className="input font-mono"
                type="number"
                min={2}
                max={30}
                step={0.5}
                value={settings.seconds_per_scene}
                onChange={field("seconds_per_scene", Number)}
              />
              <span className="absolute right-3.5 top-2.5 font-mono text-xs text-slate-400">dtk/frame</span>
            </div>
          </Field>
          <Field label="Style Gambar Default">
            <Select
              value={settings.default_style_id}
              onChange={(v) => update({ default_style_id: v })}
              options={styles.map((s) => ({ value: s.id, label: s.name }))}
            />
          </Field>
          <Field label="Bahasa Narasi Default">
            <input className="input" value={settings.default_language} onChange={field("default_language")} />
          </Field>
        </div>
      </Section>

      <Section
        title="Suara & TTS (Langkah 2 Audio)"
        desc="Pengaturan suara referensi default dan parameter model kloning audio (OmniVoice / VoxCPM2) untuk narasi per adegan."
        icon={AudioLines}
      >
        <div className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Suara Referensi Default" hint="Suara kloning yang otomatis dipakai saat membuat project baru.">
              <div className="flex items-center gap-1.5">
                <Select
                  className="flex-1"
                  value={settings.tts_voice_id ?? ""}
                  onChange={(v) => update({ tts_voice_id: v || null })}
                  options={[
                    { value: "", label: "Belum dipilih (pilih suara referensi)" },
                    ...voices.map((v) => ({
                      value: v.id,
                      label: `${v.name} (${(v.speed ?? (v.id === "suara-2" ? 0.9 : 1.0)).toFixed(2)}x)`,
                      desc: `${v.duration.toFixed(1)} dtk · kecepatan ${(v.speed ?? (v.id === "suara-2" ? 0.9 : 1.0)).toFixed(2)}x`,
                    })),
                  ]}
                />
                {settings.tts_voice_id && (
                  <button
                    type="button"
                    className={`btn-ghost px-2.5 py-2 transition ${playingVoiceId === settings.tts_voice_id ? "text-amber-300 bg-amber-500/15" : ""}`}
                    onClick={() => toggleVoicePlay(settings.tts_voice_id)}
                    title={playingVoiceId === settings.tts_voice_id ? "Hentikan contoh suara" : "Putar contoh suara"}
                    aria-label={playingVoiceId === settings.tts_voice_id ? "Hentikan contoh suara" : "Putar contoh suara"}
                  >
                    {playingVoiceId === settings.tts_voice_id ? <Pause size={14} /> : <Play size={14} />}
                  </button>
                )}
              </div>
              {settings.tts_voice_id && (
                <div className="pt-2">
                  <SliderField
                    label={`Kecepatan Default (${voices.find((v) => v.id === settings.tts_voice_id)?.name ?? "Suara"})`}
                    hint="Faktor pengali kecepatan vokal khusus untuk suara ini (otomatis tersimpan)."
                    value={
                      voices.find((v) => v.id === settings.tts_voice_id)?.speed ??
                      (settings.tts_voice_id === "suara-2" ? 0.9 : 1.0)
                    }
                    min={0.5}
                    max={2.0}
                    step={0.05}
                    defaultValue={settings.tts_voice_id === "suara-2" ? 0.9 : 1.0}
                    unit="x"
                    onChange={async (v) => {
                      const spd = parseFloat(v);
                      try {
                        await api.setVoiceSpeed(settings.tts_voice_id, spd);
                        setVoices((prev) =>
                          prev.map((item) => (item.id === settings.tts_voice_id ? { ...item, speed: spd } : item))
                        );
                      } catch (err) {
                        console.error("Gagal update kecepatan suara di Settings:", err);
                      }
                    }}
                  />
                </div>
              )}
            </Field>

            <Field label="Model TTS Default" hint="Pilih arsitektur model default yang digunakan worker.">
              <ChoiceCards
                className="grid-cols-2"
                value={settings.tts_model || "omnivoice"}
                onChange={(v) => update({ tts_model: v })}
                options={[
                  {
                    value: "omnivoice",
                    label: "OmniVoice",
                    desc: "24 kHz · ringan, cocok untuk Mac",
                  },
                  {
                    value: "voxcpm2",
                    label: "VoxCPM2",
                    desc: "48 kHz · lebih berat, paling enak di GPU NVIDIA",
                  },
                ]}
              />
            </Field>
          </div>

          <div className="rounded-xl border border-[#292e3b] bg-[#12141a]/60 p-4 space-y-4">
            <div className="flex items-center justify-between border-b border-[#292e3b] pb-2.5">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-300">
                Parameter Tuning OmniVoice (24 kHz)
              </span>
              <span className="font-mono text-[11px] text-slate-400">Default Model</span>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <SliderField
                label="Inference Steps (num_step)"
                hint="Langkah difusi audio (4–64). Nilai lebih tinggi meningkatkan kejelasan suara."
                value={settings.omnivoice?.num_step}
                min={4}
                max={64}
                step={1}
                defaultValue={16}
                onChange={(v) => update({ omnivoice: { ...(settings.omnivoice || {}), num_step: v } })}
              />
              <SliderField
                label="Guidance Scale"
                hint="Kekuatan kepatuhan terhadap prompt suara referensi (0–5)."
                value={settings.omnivoice?.guidance_scale}
                min={0}
                max={5}
                step={0.1}
                defaultValue={3.0}
                onChange={(v) => update({ omnivoice: { ...(settings.omnivoice || {}), guidance_scale: v } })}
              />
              <SliderField
                label="Time Shift (t_shift)"
                hint="Offset kurva noise schedule difusi (0–1)."
                value={settings.omnivoice?.t_shift}
                min={0}
                max={1}
                step={0.05}
                defaultValue={0.1}
                onChange={(v) => update({ omnivoice: { ...(settings.omnivoice || {}), t_shift: v } })}
              />
              <SliderField
                label="Kecepatan Bicara (speed)"
                hint="Faktor pengali kecepatan vokal (0.5x–2.0x)."
                value={settings.omnivoice?.speed}
                min={0.5}
                max={2.0}
                step={0.05}
                defaultValue={1.0}
                unit="x"
                onChange={(v) => update({ omnivoice: { ...(settings.omnivoice || {}), speed: v } })}
              />
            </div>
          </div>

          <div className="rounded-xl border border-[#292e3b] bg-[#12141a]/60 p-4 space-y-4">
            <div className="flex items-center justify-between border-b border-[#292e3b] pb-2.5">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-300">
                Parameter Tuning VoxCPM2 (48 kHz)
              </span>
              <span className="font-mono text-[11px] text-emerald-400">CUDA / NVIDIA Recommended</span>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <SliderField
                label="CFG Value"
                hint="Classifier-Free Guidance untuk kestabilan intonasi VoxCPM2 (1–5)."
                value={settings.voxcpm2?.cfg_value}
                min={1}
                max={5}
                step={0.1}
                defaultValue={2.5}
                onChange={(v) => update({ voxcpm2: { ...(settings.voxcpm2 || {}), cfg_value: v } })}
              />
              <SliderField
                label="Inference Timesteps"
                hint="Jumlah langkah inferensi VoxCPM2 (4–50)."
                value={settings.voxcpm2?.inference_timesteps}
                min={4}
                max={50}
                step={1}
                defaultValue={10}
                onChange={(v) => update({ voxcpm2: { ...(settings.voxcpm2 || {}), inference_timesteps: v } })}
              />
            </div>
            <div className="pt-1">
              <Toggle
                checked={settings.voxcpm2?.studio_clean ?? true}
                onChange={(v) => update({ voxcpm2: { ...(settings.voxcpm2 || {}), studio_clean: v } })}
                label="Studio Clean Master"
                desc="Membersihkan desis frekuensi tinggi 12 kHz+ pada vocoder VoxCPM2 dan gate noise floor antar jeda kata."
              />
            </div>
          </div>
        </div>
      </Section>

      <Section title="Tempo Kerja Worker (Google Flow)" desc="Mengatur kecepatan Chrome extension berinteraksi dengan Google Flow. Menggunakan metode paste instan agar proses cepat dan efisien." icon={Sliders}>
        <ChoiceCards
          className="sm:grid-cols-4"
          value={settings.tempo_preset}
          onChange={(key) => key !== "custom" && update({ tempo_preset: key, ...PRESETS[key].values })}
          options={[
            ...Object.entries(PRESETS).map(([key, p]) => ({ value: key, label: p.label, desc: p.desc })),
            { value: "custom", label: "Custom", desc: "Aktif saat nilai jeda diubah manual", disabled: settings.tempo_preset !== "custom" },
          ]}
        />
        <div className="grid gap-4 sm:grid-cols-3 pt-2">
          <Field label="Jeda Antar Gambar (detik)" hint="Waktu jeda setelah gambar selesai sebelum mengambil job berikutnya.">
            <RangeInput value={settings.delay_between_images} onChange={pacing("delay_between_images")} unit="dtk" step={1} />
          </Field>
          <Field label="Jeda Antar Ambil Ulang 2K (detik)" hint="Jeda saat proses unduh ulang file 2K full-res.">
            <RangeInput value={settings.delay_between_redownloads} onChange={pacing("delay_between_redownloads")} unit="dtk" step={1} />
          </Field>
          <Field label="Jeda Sebelum Klik Kirim (detik)" hint="Buffer sesaat setelah paste agar input Flow stabil sebelum send.">
            <RangeInput value={settings.before_send} onChange={pacing("before_send")} unit="dtk" step={0.1} />
          </Field>
        </div>
      </Section>

      <Section title="Concurrent Generation (Multi-Worker)" desc="Memproses beberapa gambar secara bersamaan di Google Flow untuk memangkas total durasi antrian." icon={Layers}>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Status Concurrent Generate" hint="Aktifkan agar antrian backend membolehkan beberapa tab Flow generate bersamaan.">
            <div className="flex items-center gap-3 pt-1">
              <Toggle
                checked={settings.concurrent_generate ?? true}
                onChange={(checked) => update({ concurrent_generate: checked })}
              />
              <span className="text-sm font-semibold text-slate-200">
                {(settings.concurrent_generate ?? true) ? "Aktif (Multi-tab Paralel)" : "Nonaktif (1 Gambar Saja)"}
              </span>
            </div>
          </Field>
          <Field label="Slot Antrian Simultan (Max Concurrency)" hint="Jumlah maksimal gambar yang diproses bersamaan (default 3).">
            <div className="relative">
              <input
                className="input font-mono font-bold text-amber-300"
                type="number"
                min={1}
                max={10}
                value={settings.max_concurrency ?? 3}
                disabled={!(settings.concurrent_generate ?? true)}
                onChange={field("max_concurrency", Number)}
              />
              <span className="absolute right-3.5 top-2.5 font-mono text-xs text-slate-400">slot simultan</span>
            </div>
          </Field>
        </div>
        <div className="rounded-lg border border-[#292e3b] bg-[#12141a] p-3 text-xs text-slate-400 leading-relaxed">
          <span className="text-amber-400 font-semibold">Cara Pakai:</span> Buka <b>{settings.max_concurrency ?? 3} tab Google Flow</b> di browser Chrome kamu dengan project yang sama. Tiap tab otomatis mengambil adegan berikutnya dan meng-generate gambar secara simultan!
        </div>
      </Section>

      <Section title="Jeda Istirahat & Pembatasan Akun" desc="Mencegah akun Google terkena rate limit atau suspend. Isi 0 untuk menonaktifkan." icon={Lock}>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Istirahat Setiap" hint="jumlah gambar ter-generate">
            <div className="relative">
              <input className="input font-mono" type="number" min={0} value={settings.break_every_images} onChange={field("break_every_images", Number)} />
              <span className="absolute right-3.5 top-2.5 font-mono text-xs text-slate-400">gambar</span>
            </div>
          </Field>
          <Field label="Durasi Istirahat">
            <RangeInput value={settings.break_minutes} onChange={(v) => update({ break_minutes: v })} unit="mnt" step={0.5} />
          </Field>
          <Field label="Batas Maksimal per Sesi" hint="Worker otomatis OFF setelah mencapai limit.">
            <div className="relative">
              <input className="input font-mono" type="number" min={0} value={settings.session_limit_images} onChange={field("session_limit_images", Number)} />
              <span className="absolute right-3.5 top-2.5 font-mono text-xs text-slate-400">gambar</span>
            </div>
          </Field>
        </div>
      </Section>

      <Section title="Penyimpanan & Resolusi Download" desc="Pengaturan ukuran file dan waktu unduh gambar dari Google Flow." icon={HardDrive}>
        <div className="space-y-4">
          <Field label="Resolusi Gambar">
            <ChoiceCards
              className="sm:grid-cols-3"
              value={settings.resolution}
              onChange={(v) => update({ resolution: v })}
              options={[
                { value: "2K", label: "2K (Ultra High-Res)", desc: "2752×1536 · AI upscale Google Flow untuk kualitas visual terbaik" },
                { value: "1K", label: "1K (Ukuran Asli Flow)", desc: "1376×768 · Ukuran asli Flow, langsung tersimpan instan tanpa upscale" },
                { value: "thumbnail", label: "Thumbnail", desc: "Pratinjau cepat ukuran ringan untuk drafting storyboard" },
              ]}
            />
          </Field>

          <Field label="Waktu Unduh (Download Mode)">
            <ChoiceCards
              className="sm:grid-cols-2"
              value={settings.download_mode || "batch_end"}
              onChange={(v) => update({ download_mode: v })}
              options={[
                {
                  value: "batch_end",
                  label: "Download di Akhir (Direkomendasikan)",
                  desc: "Gambar 1K langsung disalin dari halaman Flow begitu selesai, tanpa klik menu. Untuk 2K: generate dulu semua scene secara paralel, lalu worker mengunduh file 2K satu per satu di akhir.",
                },
                {
                  value: "immediate",
                  label: "Download Langsung per Scene",
                  desc: "Membuka menu download Flow setiap kali 1 gambar selesai. Perhatian: bisa terjadi perebutan klik mouse saat generate paralel aktif.",
                },
              ]}
            />
          </Field>
        </div>
      </Section>

      <Section
        title="Penyimpanan Cloud Multi-Device (Cloudflare D1 & R2)"
        desc="Sinkronisasi database D1 dan media object storage R2 agar proyek dan aset otomatis sinkron antara Mac dan Windows."
        icon={Cloud}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          {/* D1 Database Status */}
          <div className="rounded-lg border border-[#292e3b] bg-[#12141a] p-4 space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
                <Database size={16} className="text-sky-400" />
                <span>Database SQLite (Cloudflare D1)</span>
              </div>
              <span
                className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium ${
                  (storageStatus?.d1_active || storageStatus?.d1_connected)
                    ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                    : "bg-slate-800 text-slate-400 border border-slate-700"
                }`}
              >
                <span className={`size-1.5 rounded-full ${(storageStatus?.d1_active || storageStatus?.d1_connected) ? "bg-emerald-400" : "bg-slate-400"}`} />
                {(storageStatus?.d1_active || storageStatus?.d1_connected) ? "Terhubung (Edge)" : "Lokal SQLite"}
              </span>
            </div>
            <p className="text-xs text-slate-400 leading-relaxed">
              Menyimpan naskah, struktur scene, dan prompt. Data otomatis sinkron instan antar laptop Mac dan PC Windows.
            </p>
            {storageStatus?.d1_database_id && (
              <p className="font-mono text-[11px] text-slate-400 truncate">
                ID: {storageStatus.d1_database_id}
              </p>
            )}
          </div>

          {/* R2 Storage Status */}
          <div className="rounded-lg border border-[#292e3b] bg-[#12141a] p-4 space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
                <Cloud size={16} className="text-amber-400" />
                <span>Object Storage (Cloudflare R2)</span>
              </div>
              <span
                className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium ${
                  (storageStatus?.r2_active || storageStatus?.r2_connected)
                    ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                    : "bg-slate-800 text-slate-400 border border-slate-700"
                }`}
              >
                <span className={`size-1.5 rounded-full ${(storageStatus?.r2_active || storageStatus?.r2_connected) ? "bg-emerald-400" : "bg-slate-400"}`} />
                {(storageStatus?.r2_active || storageStatus?.r2_connected) ? "Terhubung (S3 API)" : "Nonaktif (Lokal Disk)"}
              </span>
            </div>
            <p className="text-xs text-slate-400 leading-relaxed">
              Tempat menyimpan gambar 2K dan file audio narasi TTS. Kuota gratis 10 GB dengan bebas biaya bandwidth keluar (Zero Egress).
            </p>
            {storageStatus?.r2_bucket && (
              <p className="font-mono text-[11px] text-slate-400">
                Bucket: <span className="text-amber-300">{storageStatus.r2_bucket}</span>
              </p>
            )}
          </div>
        </div>

        {/* R2 Usage Meter */}
        {storageStatus?.r2_stats && (
          <div className="rounded-lg border border-[#292e3b] bg-[#12141a] p-4 space-y-3">
            <div className="flex items-center justify-between text-xs">
              <span className="font-medium text-slate-300">Penggunaan Kuota Free Tier R2 (Maks 10 GB)</span>
              <span className="font-mono text-slate-400">
                <b className="text-amber-300">{storageStatus.r2_stats.used_mb} MB</b> / 10,000 MB ({storageStatus.r2_stats.percent_used}%)
              </span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-[#1b1e26]">
              <div
                className={`h-full transition-all duration-500 ${
                  storageStatus.r2_stats.percent_used > 85
                    ? "bg-red-500"
                    : storageStatus.r2_stats.percent_used > 60
                    ? "bg-amber-500"
                    : "bg-emerald-500"
                }`}
                style={{ width: `${Math.min(100, Math.max(1, storageStatus.r2_stats.percent_used))}%` }}
              />
            </div>
            <div className="flex items-center justify-between text-[11px] text-slate-400">
              <span>{storageStatus.r2_stats.total_objects} total objek media tersimpan di cloud</span>
              <span>Sisa kuota gratis: {Math.max(0, 10 - storageStatus.r2_stats.used_gb).toFixed(2)} GB</span>
            </div>
          </div>
        )}

        {/* 30 Projects Cap & GDrive Backup Recommendation */}
        <div className="rounded-lg border border-[#292e3b] bg-[#12141a] p-4 space-y-3">
          <div className="flex items-center justify-between text-xs">
            <span className="font-medium text-slate-300">Akumulasi Project Aktif di Cloud</span>
            <span className="font-mono text-slate-400">
              <b className={storageStatus?.needs_backup ? "text-amber-400" : "text-slate-200"}>
                {storageStatus?.total_projects ?? 0}
              </b>{" "}
              / {storageStatus?.backup_threshold ?? 30} proyek rekomendasi
            </span>
          </div>

          <div className="h-2 w-full overflow-hidden rounded-full bg-[#1b1e26]">
            <div
              className={`h-full transition-all duration-500 ${
                (storageStatus?.total_projects ?? 0) >= (storageStatus?.backup_threshold ?? 30)
                  ? "bg-amber-400"
                  : "bg-sky-500"
              }`}
              style={{
                width: `${Math.min(100, (((storageStatus?.total_projects ?? 0) / (storageStatus?.backup_threshold ?? 30)) * 100))}%`,
              }}
            />
          </div>

          {storageStatus?.needs_backup && (
            <div className="flex items-start gap-2.5 rounded border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200 leading-relaxed">
              <AlertCircle size={16} className="shrink-0 text-amber-400 mt-0.5" />
              <div>
                <b>Batas 30 Proyek Tercapai:</b> Proyek yang sudah selesai dan tayang di YouTube disarankan untuk di-backup ke Google Drive via <code>rclone</code>, kemudian dibersihkan dari R2 agar ruang cloud tetap leluasa.
              </div>
            </div>
          )}

          {/* Isolated Google Drive Account Info */}
          <div className="rounded-lg border border-[#21242d] bg-[#0c0d12] p-3 text-xs space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-slate-200">
                Akun Google Drive: <span className="text-amber-300 font-mono">{storageStatus?.gdrive_email || "aseplandak02@gmail.com"}</span>
              </span>
              <span
                className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium ${
                  storageStatus?.gdrive_configured
                    ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                    : "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                }`}
              >
                <span className={`size-1.5 rounded-full ${storageStatus?.gdrive_configured ? "bg-emerald-400" : "bg-amber-400"}`} />
                {storageStatus?.gdrive_configured ? "Terhubung" : "Belum Login"}
              </span>
            </div>
            <p className="text-[11px] text-slate-400 leading-relaxed">
              Koneksi terisolasi di file lokal <code className="text-slate-300">{storageStatus?.rclone_config_path || "data/rclone.conf"}</code>, terpisah penuh dari environment luar atau akun Google Drive lain di komputer.
            </p>
          </div>

          {storageStatus?.rclone_backup_command && (
            <div className="space-y-1.5 pt-1">
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold text-slate-300">Perintah Backup Rclone (R2 → Google Drive)</label>
                <button
                  type="button"
                  onClick={() => {
                    navigator.clipboard.writeText(storageStatus.rclone_backup_command);
                    setCopiedRclone(true);
                    setTimeout(() => setCopiedRclone(false), 2000);
                  }}
                  className="flex items-center gap-1 text-[11px] font-medium text-amber-400 hover:text-amber-300"
                >
                  {copiedRclone ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}
                  <span>{copiedRclone ? "Tersalin!" : "Salin Perintah"}</span>
                </button>
              </div>
              <pre className="rounded bg-[#0c0d12] border border-[#21242d] p-3 text-[11px] font-mono text-slate-300 overflow-x-auto whitespace-pre-wrap break-all select-all">
                {storageStatus.rclone_backup_command}
              </pre>
              <p className="text-[11px] text-slate-400">
                Jalankan perintah ini di Terminal, atau cukup klik 2x <code className="text-amber-300">backup.bat</code> (Windows) / <code className="text-amber-300">./backup.sh</code> (Mac) di folder aplikasi untuk menu interaktif otomatis.
              </p>
            </div>
          )}
        </div>
      </Section>

      <Section title="Notifikasi Sistem" desc="Notifikasi pop-up desktop saat tugas latar belakang selesai." icon={Volume2}>
        <Toggle
          checked={settings.notifications}
          onChange={(v) => update({ notifications: v })}
          label="Kirim notifikasi Chrome Extension"
          desc="Mengirim sinyal suara/notifikasi saat project selesai, batas sesi tercapai, atau ada error berulang."
        />
      </Section>

      <details className="panel p-5 group">
        <summary className="cursor-pointer font-bold text-sm text-slate-300 hover:text-white select-none flex items-center justify-between">
          <span>Pengaturan Lanjutan & Batas Waktu</span>
          <span className="text-xs font-mono text-slate-500 group-open:rotate-180 transition-transform">▼</span>
        </summary>
        <div className="mt-4 pt-4 border-t border-[#292e3b] sm:max-w-sm">
          <Field label="Batas Waktu Tunggu Frame Flow (detik)" hint="Jika gambar tidak muncul dalam durasi ini, adegan ditandai gagal dan worker beralih ke adegan berikutnya.">
            <div className="relative">
              <input className="input font-mono" type="number" min={30} max={1800} value={settings.image_timeout_sec} onChange={field("image_timeout_sec", Number)} />
              <span className="absolute right-3.5 top-2.5 font-mono text-xs text-slate-400">detik</span>
            </div>
          </Field>
        </div>
      </details>

      {/* Floating Save Bar */}
      <div className="fixed inset-x-0 bottom-0 z-40 border-t border-[#292e3b] bg-[#0e1015]/95 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-3 px-4 py-3.5">
          <span className={`text-xs font-mono ${message?.error ? "text-red-400" : dirty ? "text-amber-400 flex items-center gap-1.5" : "text-slate-400 flex items-center gap-1.5"}`}>
            {dirty && <span className="size-2 rounded-full bg-amber-400 animate-pulse" />}
            {!dirty && !message?.error && <span className="size-2 rounded-full bg-emerald-400" />}
            {message?.text ?? (dirty ? "Ada perubahan pengaturan belum disimpan" : "Semua pengaturan tersimpan")}
          </span>
          <button className="btn-primary" disabled={!dirty || saving} onClick={save}>
            <Save size={15} /> {saving ? "Menyimpan…" : "Simpan Pengaturan"}
          </button>
        </div>
      </div>
    </div>
  );
}
