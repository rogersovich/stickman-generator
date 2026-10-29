// Runs inside the Google Flow tab. Pulls jobs from the local backend, types the
// prompt like a person, submits it, waits for the new image and uploads it back.
//
// Flow's DOM changes often. If something breaks, tweak SELECTORS / the find* helpers.

const SELECTORS = {
  // placeholder / aria-label of the prompt box
  inputHint: /apa yang ingin|what do you want|prompt|describe|buat/i,
  // aria-label / text of the send button (Material icon text included)
  // exact send button seen in Flow (Angular Material): aria-label "Mulai pembuatan", icon arrow_forward
  sendButton: 'button.generate-icon-button, button[aria-label="Mulai pembuatan"], button[aria-label="Start generating"]',
  sendHint: /mulai pembuatan|start generat|send|kirim|submit|arrow_forward|arrow_upward|generate/i,
  // buttons in the prompt box that are NOT the send button
  notSendHint: /close|tutup|hapus|clear|add|tambah|upload|lampir|setelan|setting|tune|storyboard|mic|voice/i,
  minImageSize: 256,
};

// Fixed internals. Everything the user can tune lives in the web UI (Pengaturan) -> GET /api/settings.
const TIMING = {
  pauseAfterPunctuation: [150, 550],
  idlePoll: [1500, 3000],
  imageStableFor: 4000,
};

// Unique tab worker identifier for multi-tab concurrent generation
const TAB_ID = Math.random().toString(36).slice(2, 6).toUpperCase();

// Used when the backend can't be reached; mirrors backend/app/settings.py defaults.
const DEFAULT_WORKER_SETTINGS = {
  think_before_typing: { min: 0, max: 0 },
  char_delay_ms: { min: 0, max: 0 },
  before_send: { min: 0.3, max: 0.8 },
  typing_mode: "fast",
  break_every_images: 0,
  break_minutes: { min: 3, max: 5 },
  session_limit_images: 0,
  resolution: "2K",
  notifications: true,
  image_timeout_sec: 240,
};

// ---------- small helpers ----------

class WorkerStopped extends Error {}

// Set synchronously when the worker is switched OFF so a running job can bail out.
let stopRequested = false;

function checkStopped() {
  if (stopRequested) throw new WorkerStopped("worker dimatikan");
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const rand = (min, max) => Math.round(min + Math.random() * (max - min));
const randRange = ([min, max]) => rand(min, max);

function send(msg) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage(msg, (res) => {
      if (chrome.runtime.lastError) return reject(new Error(chrome.runtime.lastError.message));
      if (res?.error) return reject(new Error(res.error));
      resolve(res?.result);
    });
  });
}

async function api(method, path, body) {
  const res = await send({ type: "api", method, path, body });
  if (!res.ok && res.status !== 204) throw new Error(`backend ${res.status}: ${JSON.stringify(res.data)}`);
  return res.data;
}

const secRange = ({ min, max }) => rand(min * 1000, max * 1000);

async function isEnabled() {
  return (await chrome.storage.local.get("enabled")).enabled === true;
}

async function loadWorkerSettings() {
  try {
    return { ...DEFAULT_WORKER_SETTINGS, ...(await api("GET", "/api/settings")) };
  } catch {
    return DEFAULT_WORKER_SETTINGS;
  }
}

// ---------- side panel log + live state ----------
// storage.local.log    = [{t, level, text}]   (last LOG_MAX entries, shown in the side panel)
// storage.local.worker = {state, label, until?, job?}  (what the worker is doing right now)

const LOG_MAX = 150;
let logChain = Promise.resolve();

function log(text, level = "info") {
  const fullText = text.startsWith("[Tab #") ? text : `[Tab #${TAB_ID}] ${text}`;
  console.log(`[stickman-worker] ${level}:`, fullText);
  logChain = logChain.then(async () => {
    const { log: entries = [] } = await chrome.storage.local.get("log");
    entries.push({ t: Date.now(), level, text: fullText });
    await chrome.storage.local.set({ log: entries.slice(-LOG_MAX) });
  });
}

let lastStateKey = "";

// state: "job" | "waiting" | "delay" | "break" | "problem" | "off"
function setState(state, label, extra = {}) {
  chrome.storage.local.set({ worker: { state, label, since: Date.now(), ...extra } });
  const key = `${state}:${label}`;
  if (key !== lastStateKey && state !== "job") log(label, state === "problem" ? "warn" : "info");
  lastStateKey = key;
}

let currentJob = null;

function step(text) {
  if (!currentJob) return;
  currentJob.step = text;
  currentJob.stepSince = Date.now();
  chrome.storage.local.set({ worker: { state: "job", label: text, since: Date.now(), job: currentJob } });
  log(`${currentJob.label}: ${text}`);
}

function notify(cfg, title, message, projectId) {
  if (!cfg?.notifications) return;
  send({ type: "notify", title, message, projectId }).catch((e) => console.warn("[stickman-worker] notify failed", e));
}

// After a job: tell the user when the whole project is finished.
async function notifyIfProjectDone(cfg, projectId) {
  try {
    const p = await api("GET", `/api/projects/${projectId}`);
    if (p.status !== "done") return;
    const done = p.scenes.filter((s) => s.image_status === "done").length;
    const failed = p.scenes.filter((s) => s.image_status === "failed").length;
    notify(cfg, "Project selesai ✓", `${p.title}\n${done} gambar selesai${failed ? `, ${failed} gagal` : ""}`, projectId);
  } catch {}
}

// Sleep that wakes up early when the worker is switched off.
async function idle(ms) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    if (!(await isEnabled())) return false;
    await sleep(Math.min(1000, end - Date.now()));
  }
  return true;
}

function isVisible(el) {
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== "hidden";
}

// Real (trusted) click via the background's chrome.debugger session; Flow ignores script clicks.
async function trustedClick(el) {
  el.scrollIntoView({ block: "nearest", inline: "nearest" });
  const r = el.getBoundingClientRect();
  await send({
    type: "trustedClick",
    x: Math.round(r.left + r.width * (0.35 + Math.random() * 0.3)),
    y: Math.round(r.top + r.height * (0.35 + Math.random() * 0.3)),
  });
}

function centerOf(el, spread = 0.3) {
  const r = el.getBoundingClientRect();
  return {
    x: Math.round(r.left + r.width * (0.5 - spread / 2 + Math.random() * spread)),
    y: Math.round(r.top + r.height * (0.5 - spread / 2 + Math.random() * spread)),
  };
}

async function trustedHover(el) {
  el.scrollIntoView({ block: "nearest", inline: "nearest" });
  await send({ type: "trustedMove", ...centerOf(el, 0.4) });
}

// ---------- Flow DOM ----------

function findInput() {
  const candidates = [...document.querySelectorAll('textarea, [contenteditable="true"], [role="textbox"]')].filter(isVisible);
  const hinted = candidates.find((el) =>
    SELECTORS.inputHint.test(
      [el.getAttribute("placeholder"), el.getAttribute("aria-label"), el.getAttribute("data-placeholder"), el.textContent?.slice(0, 60)].join(" ")
    )
  );
  return hinted || candidates.at(-1) || null;
}

function describe(el) {
  const label = [el.getAttribute("aria-label"), el.getAttribute("title"), el.textContent?.trim()].filter(Boolean).join(" / ");
  const r = el.getBoundingClientRect();
  return `<${el.tagName.toLowerCase()}> "${label.slice(0, 40)}" @${Math.round(r.right)},${Math.round(r.bottom)}${el.disabled || el.getAttribute("aria-disabled") === "true" ? " disabled" : ""}`;
}

function buttonText(b) {
  return [b.getAttribute("aria-label"), b.getAttribute("title"), b.textContent].join(" ");
}

// Buttons of the prompt box: the smallest ancestor of the input that holds 2+ buttons.
function composerButtons(input) {
  let node = input.parentElement;
  for (let depth = 0; depth < 8 && node; depth++, node = node.parentElement) {
    const buttons = [...node.querySelectorAll('button, [role="button"]')].filter(isVisible);
    if (buttons.length >= 2) return buttons;
  }
  return [];
}

function findSendButton(input) {
  const exact = [...document.querySelectorAll(SELECTORS.sendButton)].filter(isVisible);
  if (exact.length) return exact.at(-1);
  const buttons = composerButtons(input);
  const hinted = buttons.filter((b) => SELECTORS.sendHint.test(buttonText(b)) && !SELECTORS.notSendHint.test(buttonText(b)));
  if (hinted.length) return hinted.at(-1);
  // fallback: the send arrow sits at the bottom-right of the prompt box
  const rest = buttons.filter((b) => !SELECTORS.notSendHint.test(buttonText(b)));
  const score = (b) => {
    const r = b.getBoundingClientRect();
    return r.bottom * 10 + r.right;
  };
  return rest.sort((a, b) => score(b) - score(a))[0] || null;
}

function inputText(el) {
  return (el.tagName === "TEXTAREA" ? el.value : el.innerText || "").trim();
}

function isDisabled(el) {
  return el.disabled || el.getAttribute("aria-disabled") === "true";
}

async function waitFor(check, ms) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    if (check()) return true;
    await sleep(250);
  }
  return check();
}

async function submitPrompt(input) {
  // Flow empties the prompt box and/or shows the prompt as a chat bubble once accepted.
  const bubbles = () => (document.body.innerText.match(/Create Image:/g) || []).length;
  const bubblesBefore = bubbles();
  const sent = () => {
    const current = findInput();
    return !current || inputText(current).length < 20 || bubbles() > bubblesBefore;
  };
  const button = findSendButton(input);
  console.log("[stickman-worker] send button:", button && describe(button));
  if (!button) throw new Error(`tombol kirim tidak ditemukan. semua tombol: ${composerButtons(input).map(describe).join("; ")}`);

  for (let attempt = 1; attempt <= 2; attempt++) {
    if (!(await waitFor(() => !isDisabled(button), 5000))) {
      throw new Error(`tombol kirim disabled: ${describe(button)} (teks prompt tidak tercatat Flow?)`);
    }
    await trustedClick(button);
    if (await waitFor(sent, 6000)) return;
  }
  throw new Error(`prompt tidak terkirim setelah 2x klik. tombol: ${describe(button)}`);
}

async function pastePrompt(el, text) {
  // Typing Enter would submit, so line breaks become spaces ("Create Image:" stays first).
  text = text.replace(/\s*\n\s*/g, " ");
  el.focus?.();
  await trustedClick(el);
  await sleep(rand(40, 80));
  await send({ type: "trustedClear" });
  await sleep(rand(40, 80));
  // Native Chrome DevTools insertText: pastes entire prompt in one call instantly
  await send({ type: "trustedType", text });

  // Ensure textarea event is fired
  if (el.tagName === "TEXTAREA" || el.tagName === "INPUT") {
    if (!el.value || el.value.length < 20) {
      el.value = text;
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
    }
  }
}

// Flow is still generating while the send button shows a stop icon (■) or a "35%" progress badge is visible.
function isGenerating() {
  const stopButton = [...document.querySelectorAll('button, [role="button"]')].some(
    (b) => isVisible(b) && (/^stop$/i.test(b.querySelector("mat-icon")?.textContent?.trim() || "") || /hentikan|berhenti|stop gen/i.test(b.getAttribute("aria-label") || ""))
  );
  if (stopButton) return true;
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const node = walker.currentNode;
    if (/^\s*\d{1,3}\s*%\s*$/.test(node.textContent) && node.parentElement && isVisible(node.parentElement)) return true;
  }
  return false;
}

function imageSrcs() {
  return new Set([...document.images].map((img) => img.currentSrc || img.src));
}

async function waitForNewImage(before, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  let candidate = null;
  let stableSince = 0;
  while (Date.now() < deadline) {
    await sleep(2000);
    checkStopped();
    const fresh = [...document.images].filter((img) => {
      const src = img.currentSrc || img.src;
      return (
        src &&
        !before.has(src) &&
        img.complete &&
        Math.max(img.naturalWidth, img.naturalHeight) >= SELECTORS.minImageSize &&
        isVisible(img)
      );
    });
    if (isGenerating()) {
      candidate = null; // ignore blurry previews until Flow is done
      continue;
    }
    // the same image appears as a grid tile and a chat thumbnail: take the biggest copy
    fresh.sort((a, b) => b.naturalWidth * b.naturalHeight - a.naturalWidth * a.naturalHeight);
    const src = fresh.length ? fresh[0].currentSrc || fresh[0].src : null;
    if (!src) continue;
    if (src !== candidate) {
      candidate = src;
      stableSince = Date.now();
    } else if (Date.now() - stableSince >= TIMING.imageStableFor) {
      return candidate;
    }
  }
  throw new Error(`timeout ${Math.round(timeoutMs / 1000)} dtk: tidak ada gambar baru dari Flow`);
}

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(",", 2)[1]);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

async function grabImage(src) {
  if (src.startsWith("data:")) {
    const [, mime, base64] = src.match(/^data:([^;]+);base64,(.*)$/) || [];
    if (!base64) throw new Error("unsupported data URL");
    return { base64, mime };
  }
  if (src.startsWith("blob:") || new URL(src).origin === location.origin) {
    const blob = await (await fetch(src, { credentials: "include" })).blob();
    return { base64: await blobToBase64(blob), mime: blob.type || "image/png" };
  }
  // cross-origin (googleusercontent etc.): fetch from the background, try full size first
  if (/googleusercontent\.com/.test(src) && /=[swh]\d+[^/]*$/.test(src)) {
    try {
      return await send({ type: "fetchImage", url: src.replace(/=[swh]\d+[^/]*$/, "=s0") });
    } catch {}
  }
  return send({ type: "fetchImage", url: src });
}

// ---------- full-resolution download through Flow's menu (⋮ → Download → 2K) ----------

async function waitForEl(find, ms) {
  let el = null;
  await waitFor(() => (el = find()), ms);
  return el;
}

// The ⋮ button that appears on an image tile while hovered.
function findTileMenuButton(img) {
  let node = img.parentElement;
  for (let depth = 0; depth < 7 && node; depth++, node = node.parentElement) {
    const btn = [...node.querySelectorAll('button, [role="button"]')].find(
      (b) =>
        isVisible(b) &&
        (/^more_(vert|horiz)$/.test(b.querySelector("mat-icon")?.textContent?.trim() || "") ||
          /lainnya|more|opsi|options/i.test(b.getAttribute("aria-label") || ""))
    );
    if (btn) return btn;
  }
  return null;
}

function findMenuItem(re) {
  const items = document.querySelectorAll('[role="menuitem"], .mat-mdc-menu-item, .cdk-overlay-pane button');
  return [...items].find((el) => isVisible(el) && !isDisabled(el) && re.test(el.innerText || "")) || null;
}

async function downloadViaMenu(src, job, resolution) {
  const tiles = [...document.images].filter((i) => (i.currentSrc || i.src) === src && isVisible(i));
  const filename = `stickman-flow/${job.project_id}/scene_${String(job.scene_index + 1).padStart(3, "0")}`;
  let lastError = "gambar tidak ditemukan di halaman";
  for (const img of tiles) {
    await trustedHover(img);
    await sleep(rand(700, 1300));
    const more = await waitForEl(() => findTileMenuButton(img), 3000);
    if (!more) {
      lastError = "tombol ⋮ tidak muncul saat hover";
      continue;
    }
    await trustedClick(more);
    await sleep(rand(500, 1000));
    const download = await waitForEl(() => findMenuItem(/download/i), 3000);
    if (!download) {
      lastError = "menu Download tidak ditemukan";
      await send({ type: "trustedEscape" });
      continue;
    }
    await trustedHover(download);
    await sleep(rand(600, 1100));
    const option = await waitForEl(() => findMenuItem(new RegExp(`(^|\\n)\\s*${resolution}\\b`)), 3000);
    if (!option) {
      lastError = `pilihan ${resolution} tidak ditemukan/terkunci`;
      await send({ type: "trustedEscape" });
      await send({ type: "trustedEscape" });
      continue;
    }
    await send({ type: "expectDownload", filename });
    await trustedClick(option);
    return send({ type: "awaitDownload" }); // absolute path of the downloaded file
  }
  throw new Error(lastError);
}

// ---------- re-download: find an existing image in Flow by the hash of its saved thumbnail ----------

async function sha256Hex(buffer) {
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

const hashCache = new Map();

async function srcHash(src) {
  if (hashCache.has(src)) return hashCache.get(src);
  let hash;
  if (src.startsWith("data:") || src.startsWith("blob:") || new URL(src).origin === location.origin) {
    hash = await sha256Hex(await (await fetch(src, { credentials: "include" })).arrayBuffer());
  } else {
    hash = await send({ type: "hashImage", url: src });
  }
  hashCache.set(src, hash);
  return hash;
}

function findScroller(el) {
  for (let node = el?.parentElement; node; node = node.parentElement) {
    const overflow = getComputedStyle(node).overflowY;
    if ((overflow === "auto" || overflow === "scroll") && node.scrollHeight > node.clientHeight + 10) return node;
  }
  return null;
}

async function findImageByHash(hash) {
  const checked = new Set();
  for (let round = 0; round < 15; round++) {
    checkStopped();
    const imgs = [...document.images].filter(
      (i) => isVisible(i) && Math.max(i.naturalWidth, i.naturalHeight) >= SELECTORS.minImageSize
    );
    for (const img of imgs) {
      const src = img.currentSrc || img.src;
      if (!src || checked.has(src)) continue;
      checked.add(src);
      try {
        if ((await srcHash(src)) === hash) {
          img.scrollIntoView({ block: "center" });
          await sleep(rand(500, 900));
          return src;
        }
      } catch (e) {
        console.warn("[stickman-worker] hash failed", src.slice(0, 60), e.message);
      }
    }
    // gallery is lazy-loaded: scroll down and look again
    const scroller = findScroller(imgs.at(-1));
    if (!scroller || scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 5) break;
    scroller.scrollBy({ top: scroller.clientHeight * 0.8, behavior: "smooth" });
    await sleep(rand(1200, 1800));
  }
  throw new Error(`gambar tidak ditemukan di halaman Flow (dicek ${checked.size} gambar). Buka project Flow tempat gambar ini dibuat.`);
}

async function runRedownload(job, cfg) {
  if (await send({ type: "attach" })) await sleep(1500);
  step("mencari gambar di Flow…");
  const src = await findImageByHash(job.thumb_sha256);
  const res = cfg.resolution === "thumbnail" ? "2K" : cfg.resolution;
  step(`download ${res}…`);
  const file = await downloadViaMenu(src, job, res);
  await api("POST", `/api/jobs/${job.project_id}/${job.scene_index}/result-file`, { path: file });
}

// ---------- job runner ----------

async function runJob(job, cfg) {
  // attach the debugger first: the "debugging" bar resizes the page, so measure positions after it
  if (await send({ type: "attach" })) await sleep(1500);
  const input = findInput();
  if (!input) throw new Error("kolom prompt Flow tidak ditemukan");

  // Tempel prompt instan via paste (tanpa jeda berpikir sebelum ketik)
  step("menempel prompt (paste instan)…");
  await pastePrompt(input, job.prompt);

  const beforeSendWait = cfg.before_send ? secRange(cfg.before_send) : 0.3;
  await sleep(Math.max(150, Math.min(beforeSendWait * 1000, 800)));
  checkStopped();
  const before = imageSrcs();
  step("mengirim prompt…");
  await submitPrompt(input);

  step("menunggu gambar dari Flow…");
  const src = await waitForNewImage(before, cfg.image_timeout_sec * 1000);
  const path = `/api/jobs/${job.project_id}/${job.scene_index}`;
  await sleep(rand(1000, 2500));

  let note = null;
  if (cfg.resolution !== "thumbnail") {
    step(`download ${cfg.resolution}…`);
    try {
      const file = await downloadViaMenu(src, job, cfg.resolution);
      await api("POST", `${path}/result-file`, { path: file });
      return;
    } catch (e) {
      if (e instanceof WorkerStopped) throw e;
      note = `resolusi rendah (thumbnail): download ${cfg.resolution} gagal: ${e.message}`;
      log(`${currentJob.label}: ${note}`, "warn");
    }
  }
  let image;
  try {
    image = await grabImage(src);
  } catch (e) {
    throw new Error(`gambar ada tapi gagal diambil (${src.slice(0, 80)}): ${e.message}`);
  }
  await api("POST", `${path}/result`, { image_base64: image.base64, mime: image.mime, note });
}

let running = false;

async function workerLoop() {
  if (running) return;
  running = true;
  stopRequested = false;
  lastStateKey = "";
  let stoppedMidJob = false;
  let generated = 0; // new images made this session (re-downloads don't count: no credits)
  let failStreak = 0; // consecutive failed jobs; notify once at 3
  log("Worker ON", "ok");
  try {
    while (await isEnabled()) {
      if (!findInput()) {
        setState("problem", "Buka sebuah project di Flow (kolom prompt belum ada)");
        if (!(await idle(5000))) break;
        continue;
      }

      let job;
      try {
        job = await api("GET", "/api/jobs/next");
      } catch (e) {
        setState("problem", `Backend tidak bisa dihubungi: ${e.message}`);
        if (!(await idle(10000))) break;
        continue;
      }
      if (!job) {
        await send({ type: "detach" }).catch(() => {}); // removes the "debugging" bar while idle
        setState("waiting", "Menunggu job dari app…");
        if (!(await idle(rand(...TIMING.idlePoll)))) break;
        continue;
      }

      const cfg = await loadWorkerSettings();
      const kindLabel = job.kind === "redownload" ? "ambil ulang" : "generate";
      currentJob = {
        label: `Scene ${job.scene_index + 1}/${job.total}`,
        project: job.project_title || job.project_id,
        scene: job.scene_index + 1,
        total: job.total,
        kind: kindLabel,
        startedAt: Date.now(),
      };
      lastStateKey = "";
      const path = `/api/jobs/${job.project_id}/${job.scene_index}`;
      try {
        if (job.kind === "redownload") await runRedownload(job, cfg);
        else await runJob(job, cfg);
        const secs = Math.round((Date.now() - currentJob.startedAt) / 1000);
        log(`${currentJob.label} (${kindLabel}) tersimpan ✓ · ${secs} dtk · ${currentJob.project}`, "ok");
        failStreak = 0;
        await notifyIfProjectDone(cfg, job.project_id);
      } catch (e) {
        if (e instanceof WorkerStopped) {
          await api("POST", `${path}/release`).catch(() => {});
          log(`Worker OFF · ${currentJob.label} dikembalikan ke antrian`, "warn");
          stoppedMidJob = true;
          break;
        }
        log(`${currentJob.label} (${kindLabel}) gagal: ${e.message}`, "error");
        await api("POST", `${path}/fail`, { error: e.message }).catch(() => {});
        failStreak += 1;
        if (failStreak === 3) {
          notify(cfg, "3 scene gagal berturut-turut", `${currentJob.project}\nError terakhir: ${e.message}`.slice(0, 300), job.project_id);
        }
        await notifyIfProjectDone(cfg, job.project_id);
      } finally {
        currentJob = null;
      }

      if (job.kind !== "redownload") {
        generated += 1;
        if (cfg.session_limit_images > 0 && generated >= cfg.session_limit_images) {
          log(`Batas sesi tercapai (${generated} gambar). Worker dimatikan otomatis.`, "warn");
          notify(cfg, "Batas sesi tercapai", `${generated} gambar dibuat sesi ini. Worker dimatikan otomatis.`, job.project_id);
          await chrome.storage.local.set({ enabled: false });
          break;
        }
        if (cfg.break_every_images > 0 && generated % cfg.break_every_images === 0) {
          const ms = rand(cfg.break_minutes.min * 60000, cfg.break_minutes.max * 60000);
          setState("break", `Istirahat ${Math.round(ms / 60000)} menit setelah ${generated} gambar`, { until: Date.now() + ms });
          if (!(await idle(ms))) break;
          continue;
        }
      }

      const wait = rand(job.delay_min * 1000, job.delay_max * 1000);
      setState("delay", `Jeda ${Math.round(wait / 1000)} dtk sebelum job berikutnya`, { until: Date.now() + wait });
      if (!(await idle(wait))) break;
    }
  } finally {
    running = false;
    currentJob = null;
    await send({ type: "detach" }).catch(() => {});
    chrome.storage.local.set({ worker: { state: "off", label: "Worker OFF", since: Date.now() } });
    if (!stoppedMidJob) log("Worker OFF");
  }
}

chrome.storage.onChanged.addListener((changes) => {
  if (!("enabled" in changes)) return;
  if (changes.enabled.newValue) workerLoop();
  else stopRequested = true;
});
isEnabled().then((on) => on && workerLoop());
