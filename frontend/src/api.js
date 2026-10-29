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
  retry: (id, i) => request("POST", `/api/projects/${id}/scenes/${i}/retry`),
  narrationOptions: (id, i, body) => request("POST", `/api/projects/${id}/scenes/${i}/narration-options`, body),
  setNarration: (id, i, narration) => request("PUT", `/api/projects/${id}/scenes/${i}/narration`, { narration }),
  redownloadAll: (id) => request("POST", `/api/projects/${id}/redownload`),
  redownload: (id, i) => request("POST", `/api/projects/${id}/scenes/${i}/redownload`),
  downloadUrl: (id) => `/api/projects/${id}/download`,
  fileUrl: (id, name, v) => `/files/${id}/${name}?v=${encodeURIComponent(v ?? "")}`,
};
