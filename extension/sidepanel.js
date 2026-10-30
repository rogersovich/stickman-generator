const DEFAULTS = {
  enabled: false,
  pausing: false,
  backendUrl: "http://localhost:8000",
  appUrl: "http://localhost:5173",
  worker: null,
  log: [],
};
const $ = (id) => document.getElementById(id);
let state = { ...DEFAULTS };

async function load() {
  state = { ...DEFAULTS, ...(await chrome.storage.local.get(Object.keys(DEFAULTS))) };
  return state;
}

function duration(ms) {
  const s = Math.max(0, Math.round(ms / 1000));
  return s < 60 ? `${s} dtk` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}d`;
}

const time = (t) => new Date(t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });

function renderState() {
  const w = state.worker;
  const live = state.enabled && w ? w : { state: "off", label: "Worker OFF" };
  $("dot").className = `dot ${live.state}`;
  $("stateLabel").textContent = live.state === "job" ? "Sedang bekerja" : live.state === "pause" ? "Menjeda…" : live.label;

  let meta = "";
  if (live.until) meta = `sisa ${duration(live.until - Date.now())}`;
  else if (live.since && live.state !== "off") meta = `sejak ${duration(Date.now() - live.since)} lalu`;
  $("stateMeta").textContent = meta;

  const job = live.state === "job" ? live.job : null;
  $("job").hidden = !job;
  if (job) {
    $("jobProject").textContent = job.project;
    $("jobScene").textContent = `${job.scene} / ${job.total}`;
    $("jobKind").textContent = job.kind;
    $("jobStep").textContent = `${job.step} (${duration(Date.now() - job.stepSince)})`;
    $("jobTotal").textContent = duration(Date.now() - job.startedAt);

    const remaining = Math.max(0, job.total - job.scene);
    const estSeconds = job.kind?.includes("2K") || job.kind?.includes("ulang")
      ? Math.round(remaining * 8)
      : Math.round((remaining * 22) / 3);
    const m = Math.floor(estSeconds / 60);
    const s = estSeconds % 60;
    $("jobEta").textContent = remaining === 0 ? "Hampir selesai ✓" : `±${m}m ${s}s (${remaining} frame)`;
  }
}

function renderLog() {
  const list = $("log");
  list.replaceChildren();
  if (!state.log.length) {
    const li = document.createElement("li");
    li.className = "empty";
    li.textContent = "Belum ada log.";
    list.append(li);
    return;
  }
  for (const entry of [...state.log].reverse()) {
    const li = document.createElement("li");
    li.className = entry.level;
    const t = document.createElement("time");
    t.textContent = time(entry.t);
    const text = document.createElement("span");
    text.className = "text";
    text.textContent = entry.text;
    li.append(t, text);
    list.append(li);
  }
}

function render() {
  const isEnabled = state.enabled;
  const isPausing = state.pausing;

  if (!isEnabled) {
    $("toggle").textContent = "Worker: OFF";
    $("toggle").className = "ghost";
    $("pauseBtn").style.display = "none";
  } else if (isPausing) {
    $("toggle").textContent = "Stop Paksa (OFF)";
    $("toggle").className = "danger";
    $("pauseBtn").style.display = "";
    $("pauseBtn").textContent = "▶ Lanjutkan";
    $("pauseBtn").className = "on";
  } else {
    $("toggle").textContent = "Worker: ON";
    $("toggle").className = "on";
    $("pauseBtn").style.display = "";
    $("pauseBtn").textContent = "⏸ Jeda (Tunggu Selesai)";
    $("pauseBtn").className = "amber";
  }

  if (document.activeElement !== $("backendUrl")) $("backendUrl").value = state.backendUrl;
  if (document.activeElement !== $("appUrl")) $("appUrl").value = state.appUrl;
  renderState();
  renderLog();
}

$("openApp").onclick = () => chrome.tabs.create({ url: state.appUrl });
$("openSettings").onclick = () => chrome.tabs.create({ url: `${state.appUrl}/#/settings` });
$("openFlowTab").onclick = async () => {
  const currentTabs = await chrome.tabs.query({ url: ["https://flow.google.com/*", "https://labs.google/*"] });
  const activeUrl = currentTabs[0]?.url || "https://flow.google.com/";
  const needed = Math.max(1, 3 - currentTabs.length);
  for (let i = 0; i < needed; i++) {
    await chrome.tabs.create({ url: activeUrl });
  }
};

$("toggle").onclick = async () => {
  const s = await load();
  if (s.enabled) {
    await chrome.storage.local.set({ enabled: false, pausing: false });
  } else {
    await chrome.storage.local.set({ enabled: true, pausing: false });
    const tabs = await chrome.tabs.query({ url: ["https://flow.google.com/*", "https://labs.google/*"] });
    if (!tabs.length) {
      const log = [...s.log, { t: Date.now(), level: "warn", text: "Buka tab Google Flow dulu, lalu buka sebuah project" }];
      chrome.storage.local.set({ log });
    }
  }
};

$("pauseBtn").onclick = async () => {
  const s = await load();
  if (!s.enabled) return;
  if (s.pausing) {
    await chrome.storage.local.set({ pausing: false });
  } else {
    await chrome.storage.local.set({ pausing: true });
  }
};

$("copyLog").onclick = async () => {
  const text = state.log.map((e) => `${time(e.t)} [${e.level}] ${e.text}`).join("\n");
  await navigator.clipboard.writeText(text || "(log kosong)");
  $("copyLog").textContent = "Tersalin ✓";
  setTimeout(() => ($("copyLog").textContent = "Copy"), 1500);
};

$("clearLog").onclick = () => chrome.storage.local.set({ log: [] });

for (const id of ["backendUrl", "appUrl"]) {
  $(id).onchange = (e) => chrome.storage.local.set({ [id]: e.target.value.trim().replace(/\/+$/, "") });
}

chrome.storage.onChanged.addListener(() => load().then(render));
setInterval(renderState, 1000); // live elapsed / countdown
load().then(render);
