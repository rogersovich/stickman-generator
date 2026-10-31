"""Pre-download model weights into TTS_HF_CACHE so the first job doesn't wait for a multi-GB download.

Usage: python worker-tts/download_models.py omnivoice|voxcpm2|all
"""

import sys

import settings
from engines import MODEL_FILES, snapshot_dir

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    targets = list(MODEL_FILES) if which == "all" else [which]
    for model_id in targets:
        if model_id not in MODEL_FILES:
            raise SystemExit(f"unknown model '{model_id}', choose: {', '.join(MODEL_FILES)} or all")
        print(f"{model_id}: downloading into {settings.HF_CACHE} …", flush=True)
        print(f"{model_id}: ready at {snapshot_dir(model_id)}")
