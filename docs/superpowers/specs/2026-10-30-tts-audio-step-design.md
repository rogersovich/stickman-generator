# Langkah 2: Audio (TTS) per scene

Status: siap direview user. Ditulis 2026-10-30.

## Intent

Setelah semua gambar scene jadi, user butuh narasi suara untuk tiap scene supaya video bisa dirakit
lalu diekspor ke CapCut. Pipeline per project jadi tiga langkah:

1. **Gambar**: sudah ada (worker Chrome extension + Google Flow).
2. **Audio**: dokumen ini. Satu klip suara per scene, dari teks `narration` scene itu.
3. **Review + Export CapCut**: project terpisah berikutnya (zoom in/out, pan, transisi, caption).
   Durasi tiap gambar di langkah 3 mengikuti panjang audio scene-nya, jadi langkah 2 harus menyimpan
   durasi audio per scene dengan akurat.

User bekerja di dua mesin: Mac (Apple M2, RAM 8 GB) dan PC Windows dengan GPU NVIDIA. Kadang app
dijalankan dari Mac dan PC menjadi worker jarak jauh; kadang semuanya dijalankan di Windows. Sistem
harus memakai GPU apa pun yang tersedia di mesin worker (CUDA, Apple MPS, atau CPU) tanpa konfigurasi
manual.

Desain ini meniru sistem TTS yang sudah terbukti di project user sendiri,
`/Users/rogersovich/Documents/Coding/Python/manhwa-recap-studio` (selanjutnya "project lama"), tapi
disederhanakan untuk kasus 1 scene = 1 klip.

## Goals

- Generate audio untuk semua scene satu project dengan sekali klik, plus generate ulang per scene.
- Dua model saja: **OmniVoice** (`k2-fsa/OmniVoice`) dan **VoxCPM2** (`openbmb/VoxCPM2`).
- Library suara (voice clone dari rekaman referensi) yang dipakai lintas project; satu suara default
  di Pengaturan, bisa diganti per project.
- Worker TTS bisa jalan di Mac (lokal) dan/atau Windows (remote), memilih device otomatis.
- Status worker kelihatan di UI: online/offline, nama mesin, device (mis. "pc-windows · CUDA").
- Audio ikut masuk ZIP project.

## Non-goals (untuk dokumen ini)

- Merakit video, preview timeline, export CapCut: project berikutnya.
- Model lain dari project lama (F5-TTS, Chatterbox, Confucius4, OmniVoice Singing), LoRA VoxCPM,
  audit intonasi, export MP3.
- Generator naskah AI (9router) tidak disentuh.

## Anti-goals (gagal walaupun "jalan")

- Backend FastAPI meng-import torch / model ML. Backend harus tetap ringan; semua ML di proses worker
  dengan venv sendiri.
- Generate audio mengganggu atau memperlambat worker gambar (Chrome extension). Keduanya independen.
- Mac 8 GB kehabisan memori karena dua model dimuat sekaligus.
- "Ulang" menghasilkan audio identik (bug project lama: seed jatuh ke 42). Ulang harus seed baru.
- Audio scene diam-diam basi: kalau teks narasi scene diubah setelah audio jadi, UI harus menandai
  audio itu perlu digenerate ulang.

## Keputusan yang sudah diambil

Dari user:
- Flow 3 langkah di atas; TTS memakai konsep project lama (worker lokal Mac + worker remote Windows,
  deteksi GPU); model hanya OmniVoice dan VoxCPM.

Keputusan Claude (user bilang "gaskan" tanpa memilih, bisa dikoreksi):
- **Letak UI**: tetap di halaman project, dipecah jadi langkah dengan URL sendiri:
  `/project/<id>/images` (halaman sekarang), `/project/<id>/audio`, `/project/<id>/export` (nanti).
  `/project/<id>` mengarah ke `/images`. Ada stepper/tab di atas panel project yang menunjukkan
  progres tiap langkah (mis. "Gambar 151/151 · Audio 0/151 · Export").
- **Suara**: library suara global + suara default di Pengaturan + override per project.
  Model dan parameter model juga: default di Pengaturan, model bisa diganti per project.
- **Impor suara lama**: sekali-jalan, impor 21 suara dari project lama (tabel `voices` di
  `manhwa-recap-studio/data/studio.db`, kolom `id, nama, transkrip, path_wav, durasi`), salin
  `ref.wav`-nya ke penyimpanan app ini.
- **Satu protokol worker**: worker Mac dan Windows sama-sama bicara HTTP ke backend (project lama
  memakai SQLite langsung untuk worker lokal; app ini menyimpan project di JSON + lock, jadi HTTP untuk
  keduanya lebih sederhana dan cuma satu jalur kode).

## Bagaimana bekerjanya

### Data

Tambahan per scene (di `Scene`): status audio (`pending | generating | done | failed`), nama file,
durasi detik, error, seed yang dipakai, suara + model yang dipakai, dan penanda teks yang dipakai
(mis. hash narasi) untuk mendeteksi audio basi. Tambahan per project: id suara dan model pilihan
(null = pakai default Pengaturan). File audio di `output/<project>/audio/scene_001.wav`.

Scene `is_merged` (gambarnya dipinjam dari scene lain) tetap punya audio sendiri: narasinya berbeda.

Library suara di `backend/data/voices/<id>/ref.wav` + metadata (nama, transkrip opsional, durasi).
Upload: 1 sampai 11.5 detik, dinormalisasi ke mono 48 kHz dengan ffmpeg (sama seperti project lama).

### Job dan worker

- Antrean audio terpisah dari antrean gambar. Unit job = 1 scene.
- Worker: `POST claim` dengan daftar model yang terpasang di mesinnya + nama worker → dapat 1 scene
  (teks, id suara, model, parameter, seed baru) atau kosong. Upload hasil WAV mentah, atau lapor gagal.
  Ambil `ref.wav` suara lewat HTTP, cache lokal per (id, mtime).
- Auth: `Authorization: Bearer <TTS_WORKER_TOKEN>` + header nama worker. Kalau token tidak diset,
  endpoint worker tidak aktif.
- Lease + heartbeat seperti project lama (heartbeat ~20 dtk, lease ~120 dtk). Scene yang lease-nya
  basi dikembalikan ke antrean; worker yang kembali setelah itu ditolak (409) untuk scene itu.
- Mode penjadwalan (env di mesin backend, seperti `NARRATION_WORKER` project lama):
  `local` (semua worker ambil), `auto` (worker Mac melewati model yang dimiliki worker remote yang
  sedang online), `remote` (worker Mac tidak ambil job).
- Backend sekarang listen di 127.0.0.1. Agar PC bisa terhubung, host backend harus bisa diset
  (mis. `0.0.0.0`, lewat Tailscale). Endpoint selain endpoint worker tetap hanya untuk localhost /
  jaringan Tailscale (pola `TrustedNetworkMiddleware` project lama).

### Proses worker

- Folder baru `worker-tts/` dengan venv sendiri `.venv-ml` (Python 3.10, torch 2.8.0, numpy 1.26.4,
  `omnivoice==0.2.1`, `voxcpm`), script setup untuk Mac (`.sh`) dan Windows (`.ps1`/`.bat`, torch
  CUDA cu128), dan script pra-unduh bobot model.
- Deteksi device: CUDA → MPS → CPU. OmniVoice: fp16 di CUDA, fp32 di MPS. VoxCPM2: TF32 di CUDA.
  `PYTORCH_ENABLE_MPS_FALLBACK=1`. Device dilaporkan di heartbeat.
- Satu model dimuat pada satu waktu; model diturunkan dari memori setelah idle (project lama: 600 dtk).
  Kelola memori sesuai catatan project lama (VoxCPM memuat safetensors ke CPU dulu; bersihkan GPU
  setelah gagal muat; jangan `empty_cache()` saat VoxCPM ter-compile di Windows).
- OmniVoice: `create_voice_clone_prompt(ref_audio, ref_text)` sekali per suara lalu dipakai ulang;
  24 kHz. VoxCPM2: `reference_wav_path` saja (transkrip diabaikan), 48 kHz, tambahkan "." di akhir
  teks tanpa tanda baca akhir (jangan "..."), `studio_clean_master` bisa dimatikan lewat env.
- Teks narasi panjang dipecah per kalimat sebelum dikirim ke model dan hasilnya disambung
  (crossfade/jeda pendek seperti `merge_files` project lama). Angka diubah ke kata Indonesia
  (`num2words`, lang `id`).

### UI langkah Audio

- Atas: pilihan suara (dengan tombol putar contoh), pilihan model, badge status worker, tombol
  "Generate semua" / "Jeda", progres (n/151, estimasi waktu).
- Daftar scene: nomor, thumbnail gambar, teks narasi (bisa diedit, reuse editor Narasi yang ada),
  player audio + durasi, status, tombol Ulang. Scene basi diberi penanda.
- Navigasi frame gagal (pill ▲▼ dari halaman Gambar) dipakai juga di sini.
- Halaman/ modal library suara: upload rekaman + nama + transkrip, putar, hapus, set default,
  tombol impor dari project lama.

## Seluruh app harus jalan di Windows (keputusan user)

User menjawab: seluruh app (backend, frontend, extension, worker TTS) harus bisa jalan di Windows,
bukan hanya worker. Dua cara pakai yang harus didukung:

- **A. App di Mac, PC jadi worker remote**: backend di Mac, worker TTS di PC Windows (CUDA) lewat
  Tailscale; worker Mac opsional.
- **B. Semua di Windows**: backend, frontend, extension Chrome, dan worker TTS lokal di satu PC.

Kondisi sekarang: kode backend sudah memakai `pathlib` dan `DOWNLOADS_DIR` default `~/Downloads`
yang juga valid di Windows; bagian yang khusus Mac adalah `run.sh` (bash, `lsof`, `sed -u`, `kill 0`).
Yang dibutuhkan:

- Launcher Windows setara `run.sh` (mis. `run.ps1` + `run.bat` pembungkus): cek port, siapkan `.env`
  dan `node_modules`, jalankan backend + frontend (+ worker TTS bila `.venv-ml` ada), hentikan semua
  saat Ctrl+C.
- Audit path Windows: pengecekan nama file di `GET /files/...` juga menolak `\`; perpindahan file
  hasil download Chrome (`save_result_file`, `is_relative_to(DOWNLOADS_DIR)`) diuji dengan path
  Windows; ffmpeg dicari di PATH dengan pesan jelas bila tidak ada.
- README: bagian setup Windows (uv, Node, ffmpeg, Chrome extension, worker TTS CUDA).

Keputusan Claude terkait ini: data project (`output/`, `backend/data/`) **tidak disinkronkan** antar
mesin. Tiap mesin punya datanya sendiri; memindahkan project antar mesin di luar cakupan.

## Keputusan dari builder check (keputusan Claude)

- **Kapan audio boleh digenerate**: kapan saja setelah project keluar dari status `draft`, tidak
  menunggu semua gambar selesai. Audio hanya butuh teks narasi. Worker TTS tidak mengalah ke worker
  gambar: worker gambar adalah otomasi Chrome yang kebanyakan menunggu Flow, jadi bentrok sumber daya
  minim. Project `draft` tidak punya audio, jadi `PUT /api/projects/{id}` yang membangun ulang scene
  tidak menghapus apa pun.
- **Bahasa**: `Project.language` dipetakan ke kode model + locale `num2words` (Indonesia → `id`,
  English → `en`); nilai lain jatuh ke `id`.
- **Audio basi**: audio scene ditandai basi kalau teks narasi, suara, atau model berubah dari yang
  dipakai saat generate. Perubahan parameter model tidak menandai basi.
- **"Generate semua"** hanya mengantrekan scene `pending`, `failed`, dan basi. Ada aksi terpisah
  "Ulang semua" (dengan konfirmasi) untuk mengulang scene yang sudah `done`.
- **Durasi**: hening di awal dan akhir tiap klip dipotong (dengan sisa margin kecil, mis. 50 ms) dan
  durasi yang disimpan adalah durasi file setelah dipotong. Jeda antar scene diatur di langkah 3.
- **Worker di PC Windows**: PC meng-clone repo ini dan menjalankan `worker-tts/` dengan `.venv-ml`
  miliknya sendiri. Lokasi cache Hugging Face bisa diset lewat env supaya bisa menunjuk ke cache
  project lama (tidak perlu unduh ulang bobot). Worker project lama dan worker app ini tidak boleh
  jalan bersamaan di GPU yang sama; README worker menyebut ini, tidak ada koordinasi otomatis.

## Diserahkan ke builder

- Bentuk persis endpoint, nama field, dan cara menyimpan status audio (asal konsisten dengan
  `storage`/`jobs` yang ada).
- Batas panjang potongan teks dan cara menyambung potongan.
- Parameter default tiap model (titik awal: nilai default di `worker-ml/engines/tts_engine.py`
  project lama) dan slider mana yang dibuka di Pengaturan.
- Apakah worker Mac dijalankan otomatis oleh `run.sh` saat `.venv-ml` ada (project lama begitu).
- Tata letak detail halaman Audio dan stepper, mengikuti gaya UI yang ada.

## Catatan risiko

- VoxCPM2 di Mac 8 GB kemungkinan lambat/berat; boleh tetap didukung, tapi worker remote Windows
  adalah jalur utama. Bobot OmniVoice belum terunduh di Mac; VoxCPM belum terpasang di Mac.
- Bug project lama yang jangan ikut tersalin: `F5Narrator._apply_speed` (VoxCPM dengan speed ≠ 1
  error), seed 42 saat regenerate, status `"completed"` vs `"done"` di UI.
