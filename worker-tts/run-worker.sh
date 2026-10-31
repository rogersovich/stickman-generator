#!/usr/bin/env bash
# Start the TTS worker (macOS / Linux)
cd "$(dirname "$0")"
export PYTORCH_ENABLE_MPS_FALLBACK=1
export PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

if [ -f ".venv-ml/bin/python" ]; then
    .venv-ml/bin/python main.py
else
    python3 main.py
fi
