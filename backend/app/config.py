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

# Cloudflare D1 & R2
CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", "")
CLOUDFLARE_D1_DATABASE_ID = os.getenv("CLOUDFLARE_D1_DATABASE_ID", "")

R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME", "stickman-genarator")
R2_ENDPOINT_URL = os.getenv("R2_ENDPOINT_URL", "")

BACKUP_PROJECT_THRESHOLD = int(os.getenv("BACKUP_PROJECT_THRESHOLD", "30"))


def has_d1() -> bool:
    return bool(CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN and CLOUDFLARE_D1_DATABASE_ID)


def has_r2() -> bool:
    return bool(R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY and R2_BUCKET_NAME and R2_ENDPOINT_URL)

