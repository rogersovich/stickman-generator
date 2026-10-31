"""Worker configuration from worker-tts/.env. Import this before torch / huggingface_hub."""

import os
import socket
from pathlib import Path

from dotenv import load_dotenv

WORKER_DIR = Path(__file__).resolve().parent
load_dotenv(WORKER_DIR / ".env")

# MPS and CUDA memory allocator defaults before torch is ever imported
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
os.environ.setdefault("PYTORCH_MPS_HIGH_WATERMARK_RATIO", "0.0")


def _path(value: str, default: Path) -> Path:
    if not value:
        return default
    p = Path(os.path.expanduser(value))
    return p if p.is_absolute() else (WORKER_DIR / p).resolve()


SERVER = os.getenv("TTS_SERVER", "http://127.0.0.1:8000")
TOKEN = os.getenv("TTS_WORKER_TOKEN", "")
NAME = os.getenv("TTS_WORKER_NAME") or socket.gethostname().split(".")[0]
HF_CACHE = _path(os.getenv("TTS_HF_CACHE", ""), WORKER_DIR / "models" / "hf_cache")
VOICE_CACHE = WORKER_DIR / "cache" / "voices"
VOXCPM_OPTIMIZE = os.getenv("VOXCPM_OPTIMIZE", "false").lower() in ("1", "true", "yes")
IDLE_UNLOAD_SECONDS = 600
HEARTBEAT_SECONDS = 20
POLL_SECONDS = 2
OFFLINE_RETRY_SECONDS = 10

# every Hugging Face download (model weights and anything a model fetches itself) goes to one cache
os.environ.setdefault("HF_HUB_CACHE", str(HF_CACHE))
