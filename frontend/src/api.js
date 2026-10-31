async function request(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {}
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.status === 204 ? null : res.json();
}

export const api = {
  config: () => request("GET", "/api/config"),
  settings: () => request("GET", "/api/settings"),
  saveSettings: (data) => request("PUT", "/api/settings", data),
  styles: () => request("GET", "/api/styles"),
  projects: () => request("GET", "/api/projects"),
  project: (id) => request("GET", `/api/projects/${id}`),
  prompts: (id) => request("GET", `/api/projects/${id}/prompts`),
  create: (data) => request("POST", "/api/projects", data),
  importMarkdown: (data) => request("POST", "/api/projects/import-markdown", data),
  parseMarkdownPreview: (markdown) => request("POST", "/api/projects/parse-markdown-preview", { markdown }),
  deleteProject: (id) => request("DELETE", `/api/projects/${id}`),
  updateDraft: (id, data) => request("PUT", `/api/projects/${id}`, data),
  confirm: (id) => request("POST", `/api/projects/${id}/confirm`),
  pause: (id) => request("POST", `/api/projects/${id}/pause`),
  resume: (id) => request("POST", `/api/projects/${id}/resume`),
  clearImages: (id) => request("POST", `/api/projects/${id}/clear-images`),
  testRun: (id, limit = 2) => request("POST", `/api/projects/${id}/test-run?limit=${limit}`),
  swapScenes: (id, a, b) => request("POST", `/api/projects/${id}/swap-scenes?a=${a}&b=${b}`),
  retry: (id, i) => request("POST", `/api/projects/${id}/scenes/${i}/retry`),
  narrationOptions: (id, i, body) => request("POST", `/api/projects/${id}/scenes/${i}/narration-options`, body),
  setNarration: (id, i, narration) => request("PUT", `/api/projects/${id}/scenes/${i}/narration`, { narration }),
  redownloadAll: (id) => request("POST", `/api/projects/${id}/redownload`),
  redownload: (id, i) => request("POST", `/api/projects/${id}/scenes/${i}/redownload`),
  voices: () => request("GET", "/api/voices"),
  storageStatus: () => request("GET", "/api/storage/status"),
  generateSceneAudio: (id, i, voiceId = "suara-1") => request("POST", `/api/projects/${id}/scenes/${i}/generate-audio?voice_id=${encodeURIComponent(voiceId)}`),
  stopAudio: (id) => request("POST", `/api/projects/${id}/stop-audio`),
  createVoice: (data) => request("POST", "/api/voices", data),
  deleteVoice: (id) => request("DELETE", `/api/voices/${id}`),
  importLegacyVoices: () => request("POST", "/api/voices/import-legacy"),
  voiceAudioUrl: (id) => `/api/voices/${id}/audio`,
  setVoiceSpeed: (voiceId, speed) => request("PUT", `/api/voices/${voiceId}/speed`, { speed }),
  setProjectTts: (id, data) => request("PUT", `/api/projects/${id}/tts`, data),
  generateAudio: (id, data) => request("POST", `/api/projects/${id}/audio/generate`, data),
  pauseAudio: (id) => request("POST", `/api/projects/${id}/audio/pause`),
  cancelAudio: (id, indices = null) => request("POST", `/api/projects/${id}/audio/cancel`, { indices }),
  ttsStatus: () => request("GET", "/api/tts/status"),
  audioUrl: (id, file, v) => `/files/${id}/${file}?v=${encodeURIComponent(v ?? "")}`,
  downloadUrl: (id) => `/api/projects/${id}/download`,
  exportCapCut: (id, options = {}) => request("POST", `/api/projects/${id}/export-capcut`, options),
  saveExportOpts: (id, data) => request("PUT", `/api/projects/${id}/export-opts`, data),
  capcutTransitions: () => request("GET", "/api/capcut/transitions"),
  sfx: () => request("GET", "/api/sfx"),
  uploadSfx: (data) => request("POST", "/api/sfx", data),
  updateSfx: (id, data) => request("PATCH", `/api/sfx/${id}`, data),
  deleteSfx: (id) => request("DELETE", `/api/sfx/${id}`),
  sfxAudioUrl: (id) => `/api/sfx/${id}/audio`,
  setSceneSfx: (id, i, data) => request("PUT", `/api/projects/${id}/scenes/${i}/sfx`, data),
  fileUrl: (id, name, v) => `/files/${id}/${name}?v=${encodeURIComponent(v ?? "")}`,
};
