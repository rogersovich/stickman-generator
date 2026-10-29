// Service worker: proxies requests to the local backend and fetches Flow images
// (host_permissions let us bypass CORS / mixed-content limits of the Flow page).

const DEFAULTS = { backendUrl: "http://localhost:8000", appUrl: "http://localhost:5173" };

async function settings() {
  return { ...DEFAULTS, ...(await chrome.storage.local.get(Object.keys(DEFAULTS))) };
}

function toBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  return btoa(binary);
}

async function callApi({ method, path, body }) {
  const { backendUrl } = await settings();
  const res = await fetch(backendUrl + path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = res.status === 204 ? null : await res.json().catch(() => null);
  return { ok: res.ok, status: res.status, data };
}

async function fetchImage({ url }) {
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) throw new Error(`image fetch ${res.status}`);
  const mime = (res.headers.get("content-type") || "image/png").split(";")[0];
  if (!mime.startsWith("image/")) throw new Error(`not an image: ${mime}`);
  return { base64: toBase64(await res.arrayBuffer()), mime };
}

// ---------- trusted input via the Chrome DevTools Protocol ----------
// Flow ignores synthetic (script) clicks, so real input events are sent through chrome.debugger.
// While attached Chrome shows a "is debugging this browser" bar; we detach when the worker turns OFF.

const attachedTabs = new Set();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const rand = (min, max) => Math.round(min + Math.random() * (max - min));

async function attach(_msg, tabId) {
  if (attachedTabs.has(tabId)) return false;
  await chrome.debugger.attach({ tabId }, "1.3");
  attachedTabs.add(tabId);
  return true; // newly attached: the debugging bar just appeared and the page resized
}

async function cdp(tabId, method, params = {}) {
  await attach(null, tabId);
  return chrome.debugger.sendCommand({ tabId }, method, params);
}

chrome.debugger.onDetach.addListener(({ tabId }) => attachedTabs.delete(tabId));

async function detachAll() {
  for (const tabId of [...attachedTabs]) {
    await chrome.debugger.detach({ tabId }).catch(() => {});
    attachedTabs.delete(tabId);
  }
}

chrome.storage.onChanged.addListener((changes) => {
  if ("enabled" in changes && !changes.enabled.newValue) detachAll();
});

async function trustedClick({ x, y }, tabId) {
  await cdp(tabId, "Input.dispatchMouseEvent", { type: "mouseMoved", x, y });
  await sleep(rand(60, 160));
  await cdp(tabId, "Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", buttons: 1, clickCount: 1 });
  await sleep(rand(50, 130));
  await cdp(tabId, "Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", buttons: 0, clickCount: 1 });
}

async function trustedMove({ x, y }, tabId) {
  await cdp(tabId, "Input.dispatchMouseEvent", { type: "mouseMoved", x, y });
}

async function trustedEscape(_msg, tabId) {
  await cdp(tabId, "Input.dispatchKeyEvent", { type: "rawKeyDown", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 });
  await cdp(tabId, "Input.dispatchKeyEvent", { type: "keyUp", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 });
}

async function trustedType({ text }, tabId) {
  await cdp(tabId, "Input.insertText", { text });
}

// Select everything in the focused field and delete it.
async function trustedClear(_msg, tabId) {
  const key = (type, extra) => cdp(tabId, "Input.dispatchKeyEvent", { type, ...extra });
  await key("rawKeyDown", { key: "a", code: "KeyA", windowsVirtualKeyCode: 65, commands: ["selectAll"] });
  await key("keyUp", { key: "a", code: "KeyA", windowsVirtualKeyCode: 65 });
  await key("rawKeyDown", { key: "Backspace", code: "Backspace", windowsVirtualKeyCode: 8 });
  await key("keyUp", { key: "Backspace", code: "Backspace", windowsVirtualKeyCode: 8 });
}

// ---------- catching Flow's own "Download 2K" file ----------
// The content script arms an expectation, clicks Download in Flow's menu, and we rename the next
// download into Downloads/stickman-flow/<project>/ and report its absolute path once complete.

let expectedQueue = []; // [{ filename, armedAt, id }]

async function expectDownload({ filename }) {
  expectedQueue.push({ filename, armedAt: Date.now(), id: null });
  return true;
}

chrome.downloads.onDeterminingFilename.addListener((item, suggest) => {
  const now = Date.now();
  // Find the first waiting expectation within 120s
  const exp = expectedQueue.find((e) => e.id === null && now - e.armedAt < 120000);
  if (exp) {
    exp.id = item.id;
    const ext = (item.filename.match(/\.(png|jpe?g|webp)$/i) || [".png"])[0].toLowerCase();
    suggest({ filename: `${exp.filename}${ext}`, conflictAction: "overwrite" });
  } else {
    suggest();
  }
});

async function awaitDownload({ timeoutMs = 180000 }) {
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) {
    const idx = expectedQueue.findIndex((e) => e.id != null);
    if (idx !== -1) {
      const exp = expectedQueue[idx];
      const [item] = await chrome.downloads.search({ id: exp.id });
      if (item?.state === "complete") {
        expectedQueue.splice(idx, 1);
        chrome.downloads.erase({ id: item.id }); // tidy Chrome's download list; the file stays
        return item.filename;
      }
      if (item?.state === "interrupted") {
        expectedQueue.splice(idx, 1);
        throw new Error(`download interrupted: ${item.error}`);
      }
    }
    await sleep(400);
  }
  throw new Error("download dari Flow tidak dimulai (menu Download tidak terklik?)");
}

async function detach(_msg, tabId) {
  if (tabId && attachedTabs.has(tabId)) {
    await chrome.debugger.detach({ tabId }).catch(() => {});
    attachedTabs.delete(tabId);
  }
  return true;
}

async function hashImage({ url }) {
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) throw new Error(`image fetch ${res.status}`);
  const digest = await crypto.subtle.digest("SHA-256", await res.arrayBuffer());
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// ---------- Chrome notifications (clicking one opens the project in the web app) ----------

const notificationLinks = new Map(); // notificationId -> app hash path

async function notify({ title, message, projectId }) {
  const id = await chrome.notifications.create({
    type: "basic",
    iconUrl: "icons/icon128.png",
    title,
    message,
    priority: 1,
  });
  if (projectId) notificationLinks.set(id, `/p/${projectId}`);
  return id;
}

chrome.notifications.onClicked.addListener(async (id) => {
  const { appUrl } = await settings();
  chrome.tabs.create({ url: `${appUrl}/#${notificationLinks.get(id) ?? "/"}` });
  chrome.notifications.clear(id);
  notificationLinks.delete(id);
});

const handlers = {
  api: callApi,
  notify,
  fetchImage,
  hashImage,
  attach,
  detach,
  trustedClick,
  trustedMove,
  trustedType,
  trustedClear,
  trustedEscape,
  expectDownload,
  awaitDownload,
};

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  const handler = handlers[msg?.type];
  if (!handler) return false;
  handler(msg, sender.tab?.id)
    .then((result) => sendResponse({ result }))
    .catch((e) => sendResponse({ error: String(e?.message || e) }));
  return true; // async response
});

// Clicking the toolbar icon opens the side panel instead of a popup.
chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(console.error);
