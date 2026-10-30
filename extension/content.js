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
  download_mode: "batch_end",
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

async function isPausing() {
  return (await chrome.storage.local.get("pausing")).pausing === true;
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
    const lowRes = (p.scenes || []).filter((s) => s.needs_hd).length;

    // If batch_end mode is active and user chose 2K, auto-transition to downloading 2K files
    if (lowRes > 0 && cfg.download_mode === "batch_end" && cfg.resolution === "2K") {
      log(`Semua prompt selesai ter-generate! Mulai mengunduh 2K (${lowRes} frame) di akhir…`, "ok");
      await api("POST", `/api/projects/${projectId}/redownload`).catch(() => {});
      return;
    }

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

// Finds the individual card element enclosing an image, stopping before multi-card containers (grid/gallery)
function findTileCard(img) {
  let card = img.parentElement;
  let curr = img.parentElement;
  while (curr && curr !== document.body) {
    const parent = curr.parentElement;
    if (!parent || parent === document.body) break;
    // Check if parent holds sibling big images outside of curr
    const siblingBigImgs = [...parent.querySelectorAll("img")].filter(
      (i) => !curr.contains(i) && isVisible(i) && Math.max(i.naturalWidth || i.width || 0, i.naturalHeight || i.height || 0) >= SELECTORS.minImageSize
    );
    if (siblingBigImgs.length > 0) {
      card = curr;
      break;
    }
    card = curr;
    curr = parent;
  }
  return card;
}

function isTileGenerating(img) {
  const card = findTileCard(img);
  if (!card) return false;
  if (card.querySelector('[role="progressbar"], mat-spinner, .mat-mdc-progress-spinner')) return true;
  for (const el of card.querySelectorAll("span, div, p")) {
    if (isVisible(el) && /^\s*\d{1,3}\s*%\s*$/.test(el.textContent || "")) return true;
  }
  return false;
}

function isSameCard(a, b) {
  if (a === b) return true;
  const cardA = findTileCard(a);
  const cardB = findTileCard(b);
  return Boolean(cardA && cardB && cardA === cardB);
}

function extractPromptKeywords(promptText) {
  if (!promptText) return [];
  const descMatch = promptText.match(/SCENE DESCRIPTION\s*([^\n]+)/i) || promptText.match(/visual focus:\s*([^\n.]+)/i);
  const source = descMatch ? descMatch[1] : promptText;
  return source
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .split(/\s+/)
    .filter((w) => w.length >= 4 && !["image", "create", "hand", "drawn", "stickman", "minimalist", "illustration", "scene", "shot"].includes(w))
    .slice(0, 8);
}

function cardMatchesJob(img, job) {
  const card = findTileCard(img);
  if (!card || !job?.prompt) return false;
  const text = (card.innerText + " " + (img.alt || "") + " " + (card.getAttribute("aria-label") || "")).toLowerCase();
  const kws = extractPromptKeywords(job.prompt);
  if (kws.length === 0) return false;
  let matches = 0;
  for (const kw of kws) {
    if (text.includes(kw)) matches++;
  }
  return matches >= 2;
}

function countGeneratingCards() {
  let count = 0;
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const node = walker.currentNode;
    if (/^\s*\d{1,3}\s*%\s*$/.test(node.textContent || "") && node.parentElement && isVisible(node.parentElement)) {
      count++;
    }
  }
  if (count === 0) {
    const spinners = [...document.querySelectorAll('[role="progressbar"], mat-spinner, .mat-mdc-progress-spinner')].filter(isVisible);
    count = spinners.length;
  }
  const stopButton = [...document.querySelectorAll('button, [role="button"]')].some(
    (b) => isVisible(b) && (/^stop$/i.test(b.querySelector("mat-icon")?.textContent?.trim() || "") || /hentikan|berhenti|stop gen/i.test(b.getAttribute("aria-label") || ""))
  );
  if (count === 0 && stopButton) {
    count = 1;
  }
  return count;
}

// Flow is still generating while the send button shows a stop icon (■) or a "35%" progress badge is visible.
function isGenerating() {
  return countGeneratingCards() > 0;
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

function grabImageFromCanvas(img) {
  try {
    const canvas = document.createElement("canvas");
    canvas.width = img.naturalWidth || img.width;
    canvas.height = img.naturalHeight || img.height;
    if (canvas.width >= 100 && canvas.height >= 100) {
      const ctx = canvas.getContext("2d");
      ctx.drawImage(img, 0, 0);
      const dataUrl = canvas.toDataURL("image/png");
      if (dataUrl && dataUrl.length > 500) {
        return { base64: dataUrl.split(",", 2)[1], mime: "image/png" };
      }
    }
  } catch {}
  return null;
}

async function grabImage(src, imgElement = null) {
  // 1. Try directly from rendered canvas in DOM if available (instant, no network)
  if (imgElement) {
    const fromCanvas = grabImageFromCanvas(imgElement);
    if (fromCanvas) return fromCanvas;
  }

  // 2. Data URL
  if (src.startsWith("data:")) {
    const [, mime, base64] = src.match(/^data:([^;]+);base64,(.*)$/) || [];
    if (!base64) throw new Error("unsupported data URL");
    return { base64, mime };
  }

  // 3. Blob URL: fetch without credentials (blob URLs reject credentials)
  if (src.startsWith("blob:")) {
    const blob = await (await fetch(src)).blob();
    return { base64: await blobToBase64(blob), mime: blob.type || "image/png" };
  }

  // 4. Same-origin fetch
  try {
    if (new URL(src, location.href).origin === location.origin) {
      const blob = await (await fetch(src)).blob();
      return { base64: await blobToBase64(blob), mime: blob.type || "image/png" };
    }
  } catch {}

  // 5. Cross-origin: fetch via background service worker, try full size first
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
  const card = findTileCard(img);
  if (!card) return null;
  return [...card.querySelectorAll('button, [role="button"]')].find(
    (b) =>
      isVisible(b) &&
      (/^more_(vert|horiz)$/.test(b.querySelector("mat-icon")?.textContent?.trim() || "") ||
        /lainnya|more|opsi|options/i.test(b.getAttribute("aria-label") || ""))
  ) || null;
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
    const optionRe = new RegExp(`(^|\\s|\\n)${resolution}\\b`, "i");
    let option = await waitForEl(() => findMenuItem(optionRe), 1500);
    if (!option) {
      // In some Angular Material menus, clicking is needed to trigger the submenu
      await trustedClick(download);
      await sleep(rand(500, 900));
      option = await waitForEl(() => findMenuItem(optionRe), 3000);
    }
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

// ---------- re-download: find an existing image in Flow by flow_src or hash ----------

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

async function findImageForJob(job) {
  const checked = new Set();
  const cleanUrl = (u) => (u || "").replace(/=[swh]\d+[^/]*$/, "");
  for (let round = 0; round < 25; round++) {
    checkStopped();
    const imgs = [...document.images].filter(
      (i) => isVisible(i) && Math.max(i.naturalWidth, i.naturalHeight) >= SELECTORS.minImageSize
    );

    // 1. Exact or clean URL match if flow_src was recorded (instant and 100% reliable)
    if (job.flow_src) {
      const match = imgs.find((i) => {
        const s = i.currentSrc || i.src;
        return s && (s === job.flow_src || cleanUrl(s) === cleanUrl(job.flow_src));
      });
      if (match) {
        match.scrollIntoView({ block: "center", behavior: "smooth" });
        await sleep(rand(400, 700));
        return match.currentSrc || match.src;
      }
    }

    // 2. Hash match fallback
    if (job.thumb_sha256) {
      for (const img of imgs) {
        const src = img.currentSrc || img.src;
        if (!src || checked.has(src)) continue;
        checked.add(src);
        try {
          if ((await srcHash(src)) === job.thumb_sha256) {
            img.scrollIntoView({ block: "center", behavior: "smooth" });
            await sleep(rand(400, 700));
            return src;
          }
        } catch (e) {
          console.warn("[stickman-worker] hash failed", src.slice(0, 60), e.message);
        }
      }
    }

    // Gallery is lazy-loaded: scroll to find older tiles
    const scroller = findScroller(imgs.at(-1)) || document.scrollingElement || document.body;
    if (scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 15) {
      if (round < 3) {
        scroller.scrollTo({ top: 0, behavior: "smooth" });
        await sleep(1000);
        continue;
      }
      break;
    }
    scroller.scrollBy({ top: scroller.clientHeight * 0.75, behavior: "smooth" });
    await sleep(rand(1000, 1500));
  }
  throw new Error(`gambar Scene ${job.scene_index + 1} tidak ditemukan di halaman Flow.`);
}

async function runRedownload(job, cfg) {
  if (await send({ type: "attach" })) await sleep(1200);
  step("mencari gambar di Flow…");
  const src = await findImageForJob(job);
  const res = cfg.resolution === "thumbnail" ? "1K" : cfg.resolution;
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
let inFlight = []; // [{ job, submittedAt }]
let completedSrcs = new Set();

async function workerLoop() {
  if (running) return;
  running = true;
  stopRequested = false;
  lastStateKey = "";
  inFlight = [];
  completedSrcs = imageSrcs();
  try {
    const activeProjects = await api("GET", "/api/projects");
    for (const p of activeProjects || []) {
      for (const s of p.scenes || []) {
        if (s.flow_src) completedSrcs.add(s.flow_src);
      }
    }
  } catch {}
  let generated = 0; // new images made this session
  let failStreak = 0; // consecutive failed jobs
  log("Worker ON", "ok");

  try {
    while (await isEnabled()) {
      checkStopped();
      const cfg = await loadWorkerSettings();
      const maxConcurrency = cfg.concurrent_generate !== false ? (cfg.max_concurrency || 3) : 1;
      const input = findInput();
      if (!input) {
        setState("problem", "Buka sebuah project di Flow (kolom prompt belum ada)");
        if (!(await idle(4000))) break;
        continue;
      }

      // Check if prompt input is ready to accept a new prompt (input exists, visible, and not containing an unsent prompt)
      const isInputReady = input && isVisible(input) && inputText(input).length < 20;
      const pausing = await isPausing();
      const activeGenerating = countGeneratingCards();
      const hasSlot = inFlight.length < maxConcurrency && activeGenerating < maxConcurrency;

      // 1. SUBMIT NEXT PROMPT ONLY IF NOT PAUSING AND UNDER CONCURRENCY LIMIT
      if (!pausing && hasSlot && isInputReady) {
        let job = null;
        try {
          job = await api("GET", "/api/jobs/next");
        } catch (e) {
          setState("problem", `Backend tidak bisa dihubungi: ${e.message}`);
          if (!(await idle(6000))) break;
          continue;
        }

        if (job) {
          if (await send({ type: "attach" })) await sleep(800);
          if (job.kind === "redownload") {
            currentJob = {
              label: `Scene ${job.scene_index + 1}/${job.total}`,
              project: job.project_title || job.project_id,
              scene: job.scene_index + 1,
              total: job.total,
              kind: "ambil ulang",
              startedAt: Date.now(),
            };
            try {
              await runRedownload(job, cfg);
              log(`${currentJob.label} (ambil ulang) tersimpan ✓`, "ok");
              await notifyIfProjectDone(cfg, job.project_id);
            } catch (e) {
              log(`${currentJob.label} ambil ulang gagal: ${e.message}`, "error");
              await api("POST", `/api/jobs/${job.project_id}/${job.scene_index}/fail`, { error: e.message }).catch(() => {});
            } finally {
              currentJob = null;
            }
          } else {
            currentJob = {
              label: `Scene ${job.scene_index + 1}/${job.total}`,
              project: job.project_title || job.project_id,
              scene: job.scene_index + 1,
              total: job.total,
              kind: "generate",
              startedAt: Date.now(),
            };
            try {
              step("menempel prompt (paste instan)…");
              await pastePrompt(input, job.prompt);
              const beforeSendMs = Math.max(200, cfg.before_send ? secRange(cfg.before_send) : 500);
              await sleep(beforeSendMs);
              checkStopped();
              step("mengirim prompt…");
              await submitPrompt(input);
              inFlight.push({ job, submittedAt: Date.now() });
              log(`Scene ${job.scene_index + 1}/${job.total} terkirim! (${inFlight.length}/${maxConcurrency} sedang diproses)`, "ok");
              setState("job", `${inFlight.length} gambar sedang diproses Flow secara paralel…`);
              // Breathing room after submitting so Flow mounts the new card cleanly before next paste
              const interPromptMs = cfg.delay_between_images ? Math.max(1000, Math.min(secRange(cfg.delay_between_images), 3500)) : 1500;
              await sleep(interPromptMs);
              continue; // check immediately if another slot can be submitted!
            } catch (e) {
              if (e instanceof WorkerStopped) throw e;
              log(`${currentJob.label} gagal kirim prompt: ${e.message}`, "error");
              await api("POST", `/api/jobs/${job.project_id}/${job.scene_index}/release`).catch(() => {});
              currentJob = null;
              await sleep(2500);
            }
          }
        }
      }

      // 2. CHECK FOR COMPLETED IMAGES FROM IN-FLIGHT GENERATIONS
      if (inFlight.length > 0) {
        const oldest = inFlight[0];
        const elapsed = Date.now() - oldest.submittedAt;

        // Flow generation takes at least 7 seconds. Ignore too-early checks to prevent matching old DOM images.
        if (elapsed >= 7000) {
          const freshImgs = [...document.images].filter((img) => {
            const src = img.currentSrc || img.src;
            return (
              src &&
              !completedSrcs.has(src) &&
              img.complete &&
              Math.max(img.naturalWidth, img.naturalHeight) >= SELECTORS.minImageSize &&
              isVisible(img) &&
              !isTileGenerating(img)
            );
          });

          if (freshImgs.length > 0) {
            // Find best match: either via keyword match or oldest FIFO (oldest submitted with oldest completed card)
            let targetIdx = -1;
            let imgIdx = -1;
            for (let i = 0; i < inFlight.length; i++) {
              const matchedImgIdx = freshImgs.findIndex((img) => cardMatchesJob(img, inFlight[i].job));
              if (matchedImgIdx !== -1) {
                targetIdx = i;
                imgIdx = matchedImgIdx;
                break;
              }
            }

            if (targetIdx === -1) {
              targetIdx = 0;
              imgIdx = freshImgs.length - 1; // oldest card in DOM (furthest down the feed)
            }

            const [target] = inFlight.splice(targetIdx, 1);
            const job = target.job;
            const freshImg = freshImgs[imgIdx];
            const src = freshImg.currentSrc || freshImg.src;
            completedSrcs.add(src);

            // Mark other image elements that belong to this same card/tile as completed too
            for (const other of freshImgs) {
              if (other === freshImg || isSameCard(other, freshImg)) {
                const s = other.currentSrc || other.src;
                if (s) completedSrcs.add(s);
              }
            }

            currentJob = {
              label: `Scene ${job.scene_index + 1}/${job.total}`,
              project: job.project_title || job.project_id,
              scene: job.scene_index + 1,
              total: job.total,
              kind: "generate",
              startedAt: target.submittedAt,
            };

            const path = `/api/jobs/${job.project_id}/${job.scene_index}`;
            const isImmediate = cfg.download_mode === "immediate";

            if (isImmediate && cfg.resolution !== "thumbnail") {
              // Immediate mode: download directly via menu per scene
              step(`download ${cfg.resolution}…`);
              let note = null;
              try {
                const file = await downloadViaMenu(src, job, cfg.resolution);
                await api("POST", `${path}/result-file`, { path: file });
              } catch (e) {
                if (e instanceof WorkerStopped) throw e;
                note = `resolusi rendah: download ${cfg.resolution} gagal: ${e.message}`;
                try {
                  const image = await grabImage(src, freshImg);
                  await api("POST", `${path}/result`, { image_base64: image.base64, mime: image.mime, flow_src: src, note });
                } catch (err) {
                  log(`${currentJob.label} gagal simpan: ${err.message}`, "error");
                  await api("POST", `${path}/fail`, { error: err.message }).catch(() => {});
                }
              }
            } else {
              // Batch-end mode (or thumbnail): grab image instantly (<200ms) without menu clicks
              step(cfg.resolution === "1K" ? "menyimpan 1K instan…" : "menyimpan pratinjau…");
              try {
                const image = await grabImage(src, freshImg);
                await api("POST", `${path}/result`, {
                  image_base64: image.base64,
                  mime: image.mime,
                  flow_src: src,
                  note: cfg.resolution === "1K" ? "1K asli" : "pratinjau siap 2K",
                });
              } catch (err) {
                log(`${currentJob.label} gagal simpan: ${err.message}`, "error");
                await api("POST", `${path}/fail`, { error: err.message }).catch(() => {});
              }
            }

            const secs = Math.round((Date.now() - target.submittedAt) / 1000);
            log(`${currentJob.label} tersimpan ✓ · ${secs} dtk (${inFlight.length} masih berjalan)`, "ok");
            failStreak = 0;
            generated += 1;
            await notifyIfProjectDone(cfg, job.project_id);
            currentJob = null;
            if (cfg.session_limit_images > 0 && generated >= cfg.session_limit_images) {
              log(`Batas sesi tercapai (${generated} gambar). Worker dimatikan otomatis.`, "ok");
              notify(cfg, "Batas sesi tercapai", `${generated} gambar selesai dibuat. Worker OFF otomatis.`, job.project_id);
              await chrome.storage.local.set({ enabled: false });
              break;
            }
            continue;
          }
        }

        // Check if oldest in-flight job timed out
        if (Date.now() - oldest.submittedAt > cfg.image_timeout_sec * 1000) {
          inFlight.shift();
          const job = oldest.job;
          log(`Scene ${job.scene_index + 1} timeout: gambar Flow tidak selesai`, "error");
          await api("POST", `/api/jobs/${job.project_id}/${job.scene_index}/fail`, { error: "timeout: gambar Flow tidak selesai" }).catch(() => {});
          failStreak += 1;
          if (failStreak === 3) {
            notify(cfg, "3 scene gagal berturut-turut", `${job.project_title}\nTimeout menunggu gambar Flow`, job.project_id);
          }
          continue;
        }
      }

      // 3. IDLE / WAITING STATE OR COMPLETE PAUSE
      if (inFlight.length === 0 && activeGenerating === 0) {
        if (pausing) {
          log("Semua proses selesai. Worker OFF otomatis (Jeda selesai) ✓", "ok");
          await chrome.storage.local.set({ enabled: false, pausing: false });
          break;
        }
        setState("waiting", "Menunggu job dari app…");
        if (!(await idle(rand(...TIMING.idlePoll)))) break;
      } else {
        const activeCount = Math.max(inFlight.length, activeGenerating);
        if (pausing) {
          setState("pause", `Menjeda: menunggu ${activeCount} proses selesai…`);
        } else {
          setState("job", `${activeCount} gambar sedang diproses Flow secara paralel…`);
        }
        if (!(await idle(1200))) break;
      }
    }
  } finally {
    running = false;
    currentJob = null;
    for (const target of inFlight) {
      await api("POST", `/api/jobs/${target.job.project_id}/${target.job.scene_index}/release`).catch(() => {});
    }
    inFlight = [];
    await send({ type: "detach" }).catch(() => {});
    await chrome.storage.local.set({ pausing: false });
    chrome.storage.local.set({ worker: { state: "off", label: "Worker OFF", since: Date.now() } });
    log("Worker OFF");
  }
}

chrome.storage.onChanged.addListener((changes) => {
  if (!("enabled" in changes)) return;
  if (changes.enabled.newValue) workerLoop();
  else stopRequested = true;
});
isEnabled().then((on) => on && workerLoop());
