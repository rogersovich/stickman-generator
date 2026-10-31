# Stickman Generator Studio

Import dokumen prompt Markdown (scene-by-scene beats & full prompts), otomatis generate gambar adegan per adegan via Google Flow Chrome Extension, lalu generate klip audio narasi per scene (Langkah 2) menggunakan arsitektur TTS voice cloning (**OmniVoice** / **VoxCPM2**).

```
frontend (React, :5173) ──► backend (FastAPI, :8000) ◄── extension (Flow tab worker)
                                    ▲
                                    │ HTTP
                                    ▼
                     worker-tts (Python ML: OmniVoice / VoxCPM2)
                     CUDA (NVIDIA) · Apple MPS · CPU
```

Pipeline 3 Langkah:
1. **1 · Gambar**: Otomasi browser Chrome di Google Flow.
2. **2 · Audio**: Satu klip suara per scene dari narasi teks, durasi terukur presisi untuk video assembly.
3. **3 · Export**: Review timeline & ekspor ZIP lengkap (gambar, audio WAV, transkrip naskah).

---

## Setup (Sekali di Awal)

### macOS / Linux
1. Backend:
   ```bash
   cd backend && cp .env.example .env
   uv sync
   ```
2. Frontend:
   ```bash
   cd frontend && npm install
   ```
3. Chrome Extension:
   - Buka `chrome://extensions` → aktifkan **Developer mode** (pojok kanan atas).
   - Klik **Load unpacked** → pilih folder `extension/`.
4. Worker TTS (Opsional untuk Langkah 2 Audio):
   ```bash
   cd worker-tts && ./setup-worker.sh
   ```

### Windows (PC)
1. Install Prasyarat:
   - Python via uv: `winget install astral-sh.uv`
   - Node.js (v20+): `winget install OpenJS.NodeJS.LTS`
   - FFmpeg (wajib ada di PATH): `winget install Gyan.FFmpeg`
2. Backend & Frontend:
   ```cmd
   cd backend && copy .env.example .env
   uv sync
   cd ..\frontend && npm install
   ```
3. Chrome Extension: Buka `chrome://extensions` → **Load unpacked** → folder `extension`.
4. Worker TTS dengan Akselerasi GPU NVIDIA (CUDA cu128):
   ```powershell
   powershell -ExecutionPolicy Bypass -File worker-tts\setup-worker.ps1
   ```

---

## Cara Menjalankan

### macOS / Linux
```bash
./run.sh
```
Menjalankan backend (:8000), frontend (:5173), dan worker TTS lokal secara bersamaan dalam satu terminal. Tekan `Ctrl+C` untuk menghentikan semuanya.

### Windows
Cukup klik ganda `run.bat` atau jalankan di PowerShell:
```cmd
run.bat
```

---

## Setup Mesin Terpisah: Mac Server + PC Windows Worker (Tailscale)

Jika backend dijalankan di Mac dan Anda ingin menggunakan GPU NVIDIA di PC Windows untuk memproses audio:

1. **Di Mac (Server)**:
   - Di `backend/.env`, set:
     ```env
     HOST=0.0.0.0
     TTS_WORKER_TOKEN=rahasia-token-anda
     TTS_WORKER_MODE=auto
     ```
   - Jalankan `./run.sh` di Mac.

2. **Di PC Windows (Worker)**:
   - Pastikan kedua mesin terhubung dalam jaringan Tailscale.
   - Di `worker-tts/.env`:
     ```env
     TTS_SERVER=http://<ip-tailscale-mac>:8000
     TTS_WORKER_TOKEN=rahasia-token-anda
     TTS_WORKER_NAME=pc-gaming
     ```
   - Jalankan worker di PC:
     ```cmd
     worker-tts\run-worker.bat
     ```
   - Di halaman Audio pada web studio Mac, badge worker akan otomatis menampilkan status hijau: `pc-gaming · CUDA · NVIDIA GeForce RTX ...`.

---

## Library Suara & Impor Suara Lama

- Aplikasi mendukung voice clone dengan referensi audio 1–11,5 detik (WAV mono 48 kHz).
- **Impor 21 Suara dari manhwa-recap-studio**:
  - Buka halaman project → tab **Audio** → klik **Kelola suara** → klik tombol **Impor dari manhwa-recap-studio**, ATAU jalankan perintah:
    ```bash
    curl -X POST http://localhost:8000/api/voices/import-legacy
    ```

---

## Cara Pakai Studio

1. Buka Web Studio di browser: `http://localhost:5173`.
2. **Buat Project**:
   - Paste dokumen Markdown naskah cerita lengkap (dengan format `# Judul`, `## Scene X`, `Beat narasi:`, dan codeblock prompt gambar).
   - Klik **Buat Project & Buka Storyboard**.
3. **Langkah 1: Gambar**:
   - Buka Google Flow di tab Chrome baru.
   - Buka ekstensi di side panel → aktifkan **Worker: ON**.
   - Gambar akan digenerate otomatis dan disinkronkan ke storage project.
4. **Langkah 2: Audio**:
   - Klik tab **2 · Audio** di atas storyboard.
   - Pilih Suara kloning dan Model (OmniVoice / VoxCPM2).
   - Klik **Generate audio** untuk membuat seluruh narasi per adegan.
   - Jika teks narasi diubah di kemudian hari, badge otomatis berubah jadi **basi** sehingga Anda tahu adegan mana yang perlu digenerate ulang.
5. **Download Hasil**:
   - Tombol **Unduh ZIP Project** di header akan mengemas semua file gambar `scene_NNN.png`, audio WAV `audio/scene_NNN.wav`, transkrip naskah, dan metadata database SQLite.
