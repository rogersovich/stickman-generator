# TTS worker

Generates the narration audio of step 2 (Audio). It runs separately from the app, in its own Python 3.10
environment (`worker-tts/.venv-ml`), so the backend never loads torch. The worker uses the best device it
finds: NVIDIA CUDA, then Apple MPS, then CPU. Models: **OmniVoice** (24 kHz, light, fine on a Mac) and
**VoxCPM2** (48 kHz, heavier, best on an NVIDIA GPU). Only one model is kept in memory; it is unloaded
after 10 minutes without jobs.

## Setup

macOS (needs `brew install python@3.10 ffmpeg`):

```bash
worker-tts/setup-worker.sh
```

Windows (needs Python 3.10 from python.org with the `py` launcher, and an NVIDIA driver):

```powershell
powershell -ExecutionPolicy Bypass -File worker-tts\setup-worker.ps1
```

Optional, so the first job doesn't wait for a multi-GB download:

```bash
worker-tts/.venv-ml/bin/python worker-tts/download_models.py all
```

Already have the weights from manhwa-recap-studio? Point `TTS_HF_CACHE` in `worker-tts/.env` at
`../manhwa-recap-studio/models/checkpoints/hf_cache` instead of downloading again.

## Run

`./run.sh` / `run.bat` start the worker together with the app when `worker-tts/.venv-ml` exists.
To run it alone: `worker-tts/.venv-ml/bin/python worker-tts/main.py` (Windows: `worker-tts\run-worker.bat`).

## Worker on another PC (app on the Mac)

1. Both machines on Tailscale.
2. Mac, `backend/.env`: `HOST=0.0.0.0`, `TTS_WORKER_TOKEN=<long random string>`, optionally
   `TTS_WORKER_MODE` (`auto`: the Mac's own worker leaves models to the online PC; `remote`: only the PC
   works; `local`: both take jobs).
3. PC, `worker-tts/.env`: `TTS_SERVER=http://<mac tailscale ip>:8000`, the same `TTS_WORKER_TOKEN`.
4. Start `worker-tts\run-worker.bat` on the PC. The Audio page shows it as online with its GPU.

Do not run the manhwa-recap-studio worker on the same GPU at the same time: two copies of a model will
not fit in VRAM.

## Tests

```bash
worker-tts/.venv-ml/bin/python -m pytest worker-tts/tests -q
```
