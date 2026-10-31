#!/usr/bin/env bash
# Start backend (FastAPI :8000) + frontend (Vite :5173) + optional TTS worker together. Ctrl+C stops all.
set -euo pipefail
cd "$(dirname "$0")"

for port in 8000 5173; do
  pids=$(lsof -ti :"$port" 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo "Port $port masih digunakan oleh proses lama ($pids). Menutup proses lama..."
    echo "$pids" | xargs kill -9 2>/dev/null || true
    sleep 0.5
  fi
done

[ -f backend/.env ] || { cp backend/.env.example backend/.env; echo "Created backend/.env - fill in the 9router settings."; }
[ -d frontend/node_modules ] || (cd frontend && npm install)

HOST="${HOST:-127.0.0.1}"
if [ "$(uname)" = "Darwin" ]; then
  # On macOS, TTS models (VoxCPM2) take ~12GB RAM which freezes 8GB/16GB Macs.
  # Keep TTS worker OFF by default on Mac; use START_TTS_WORKER=1 ./run.sh to force it.
  START_TTS_WORKER="${START_TTS_WORKER:-0}"
else
  START_TTS_WORKER="${START_TTS_WORKER:-1}"
fi

(cd backend && uv run uvicorn app.main:app --reload --host "$HOST" --port 8000 2>&1 | sed -u 's/^/[backend]  /') &
(cd frontend && npm run dev -- --strictPort 2>&1 | sed -u 's/^/[frontend] /') &

if [ "$START_TTS_WORKER" != "0" ] && [ -x worker-tts/.venv-ml/bin/python ]; then
  (worker-tts/.venv-ml/bin/python worker-tts/main.py 2>&1 | sed -u 's/^/[tts]       /') &
fi

trap 'echo; echo "Stopping..."; kill 0' INT TERM EXIT

echo "App: http://localhost:5173   (Ctrl+C to stop)"
wait
