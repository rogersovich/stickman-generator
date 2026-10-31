#!/usr/bin/env bash
# Create worker-tts/.venv-ml (Python 3.10) and install the TTS worker. macOS / Linux.
set -euo pipefail
cd "$(dirname "$0")"

PY="$(command -v python3.10 || true)"
if [ -z "$PY" ]; then
  echo "python3.10 not found. Install it first: brew install python@3.10"
  exit 1
fi

[ -d .venv-ml ] || "$PY" -m venv .venv-ml
.venv-ml/bin/python -m pip install --upgrade pip
.venv-ml/bin/python -m pip install -r requirements.txt
if ! .venv-ml/bin/python -m pip install voxcpm; then
  echo "WARNING: voxcpm failed to install; the worker will only offer OmniVoice."
fi
[ -f .env ] || cp .env.example .env
echo "Done. Start the worker with: worker-tts/.venv-ml/bin/python worker-tts/main.py"
