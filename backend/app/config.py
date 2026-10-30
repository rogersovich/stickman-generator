import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")


def _list(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def _path(value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else (BACKEND_DIR / p).resolve()


NINEROUTER_BASE_URL = os.getenv("NINEROUTER_BASE_URL", "http://localhost:20128/v1").rstrip("/")
NINEROUTER_API_KEY = os.getenv("NINEROUTER_API_KEY", "")
NINEROUTER_MODEL = os.getenv("NINEROUTER_MODEL", "")
# tried in order when the main model errors or returns unusable output
NINEROUTER_FALLBACK_MODELS = _list(os.getenv("NINEROUTER_FALLBACK_MODELS", ""))
# models offered in the web UI; the main + fallback models are always included
NINEROUTER_MODEL_CHOICES = list(
    dict.fromkeys([NINEROUTER_MODEL, *_list(os.getenv("NINEROUTER_MODEL_CHOICES", "")), *NINEROUTER_FALLBACK_MODELS])
)
NINEROUTER_MODEL_CHOICES = [m for m in NINEROUTER_MODEL_CHOICES if m]
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "900"))

OUTPUT_DIR = _path(os.getenv("OUTPUT_DIR", "../output"))
# Chrome's download folder: full-res images downloaded from Flow land here before being moved to OUTPUT_DIR
DOWNLOADS_DIR = Path(os.path.expanduser(os.getenv("DOWNLOADS_DIR", "~/Downloads"))).resolve()
STYLES_DIR = BACKEND_DIR / "styles"

SECONDS_PER_SCENE = float(os.getenv("SECONDS_PER_SCENE", "7"))
DELAY_BETWEEN_IMAGES_MIN = float(os.getenv("DELAY_BETWEEN_IMAGES_MIN", "20"))
DELAY_BETWEEN_IMAGES_MAX = float(os.getenv("DELAY_BETWEEN_IMAGES_MAX", "60"))
# re-downloading an existing image needs no generation, so it can go faster
REDOWNLOAD_DELAY_MIN = float(os.getenv("REDOWNLOAD_DELAY_MIN", "3"))
REDOWNLOAD_DELAY_MAX = float(os.getenv("REDOWNLOAD_DELAY_MAX", "8"))
JOB_TIMEOUT_SECONDS = float(os.getenv("JOB_TIMEOUT_SECONDS", "300"))

# narration audio (TTS)
VOICES_DIR = _path(os.getenv("VOICES_DIR", "data/voices"))
# shared secret for TTS workers on other machines; empty = only workers on this machine (localhost)
TTS_WORKER_TOKEN = os.getenv("TTS_WORKER_TOKEN", "")
# local: every worker takes jobs | auto: this machine's worker skips models an online remote worker has
# remote: this machine's worker never takes jobs
TTS_WORKER_MODE = os.getenv("TTS_WORKER_MODE", "auto")
if TTS_WORKER_MODE not in ("local", "auto", "remote"):
    TTS_WORKER_MODE = "auto"
# voice library of manhwa-recap-studio, imported once from the voice library screen
LEGACY_STUDIO_DB = Path(
    os.path.expanduser(os.getenv("LEGACY_STUDIO_DB", "~/Documents/Coding/Python/manhwa-recap-studio/data/studio.db"))
)
TTS_LEASE_SECONDS = 120  # a generating scene goes back to the queue when its worker is silent this long
TTS_SEEN_SECONDS = 30  # a worker counts as online when it called in this recently
