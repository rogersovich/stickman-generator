# Stickman Generator Studio

Generate narrated story drafts via LLM (9router) or **import ready-to-run Markdown prompt documents** (with scene-by-scene beats & full prompts), then auto-generate one Google Flow image per scene via a Chrome extension. Images land in `output/<project>/`.

```
frontend (React, :5173) ──► backend (FastAPI, :8000) ◄── extension (Flow tab worker)
                                    │
                               9router (LLM)        output/<project>/scene_001.png …
                                    or
                         Markdown Prompts Import
```

## Setup (once)

1. `cd backend && cp .env.example .env` → fill `NINEROUTER_BASE_URL`, `NINEROUTER_API_KEY`, `NINEROUTER_MODEL` (optional if using Markdown Import)
2. `cd backend && uv sync`
3. `cd frontend && npm install`
4. Chrome → `chrome://extensions` → Developer mode ON → **Load unpacked** → pick the `extension/` folder

## Run

```bash
./run.sh
```

Starts backend (:8000) + frontend (:5173) in one terminal. Ctrl+C stops both.

## Use

### Mode A: Import Markdown Prompts (Recommended)
1. Buka App (`http://localhost:5173`).
2. Pilih tab **Import Markdown Prompts**.
3. Upload file `.md` (misal `prompts.md`) atau paste langsung isinya:
   - Judul diambil dari `# Judul Cerita`
   - Setiap adegan diambil dari `## Scene X`
   - Naskah narasi otomatis diekstrak dari baris `Beat narasi:`
   - Prompt gambar otomatis diekstrak dari codeblock ``` `CREATE IMAGE...` ```
   - Adegan split-screen / gabungan (e.g. `DIGABUNG KE SCENE 27`) otomatis dideteksi dan tidak memotong kuota Flow ganda.
4. Klik **Buat Project & Buka Storyboard**.
5. Buka tab Google Flow di browser → aktifkan **Worker: ON** di side panel extension.
6. Pantau progress real-time:
   - **Voiceover (Suara 1)**: Klik tombol **Generate Audio (Suara 1)** di toolbar atau ikon `+ Suara 1` di tiap card frame untuk membuat suara narasi beresolusi studio 48kHz (VoxCPM2 + LoRA custom suaramu).
   - **Download ZIP**: Berisi seluruh gambar terurut `scene_001.png`, audio narasi `scene_001.wav`, `narration.txt`, dan `project.json` yang siap langsung di-drag ke video editor (CapCut, Premiere, DaVinci).

### Mode B: Generate Naskah dengan AI
1. Pilih tab **Generate dengan AI (9router)**.
2. Isi topik cerita, format (9:16 / 16:9), target durasi.
3. Review & edit draf adegan → Konfirmasi & Generate.

## Tuning

- **Web app → ⚙ Pengaturan**: default model/style/language, seconds per scene, worker tempo presets (Santai/Normal/Cepat or custom delays), typing mode, breaks every N images, session image limit, download resolution, image timeout. Saved in `backend/settings.json`.
- Selector Google Flow: Jika tampilan UI Google Flow berubah, sesuaikan selector di `extension/content.js`.
- Style Gambar Baru: Tambahkan konfigurasi JSON di `backend/styles/`.

> Automating Google Flow may violate Google's Terms of Service and can get the account rate-limited or banned. Keep batches small and delays long.
