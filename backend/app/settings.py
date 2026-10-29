"""User settings edited in the web UI (Pengaturan page) and read by the extension.

Stored in backend/settings.json. Values from .env are only the initial defaults.
"""

import threading
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from . import config

SETTINGS_FILE = config.BACKEND_DIR / "settings.json"
_lock = threading.Lock()


class Range(BaseModel):
    min: float = Field(ge=0)
    max: float = Field(ge=0)

    @model_validator(mode="after")
    def _ordered(self):
        if self.max < self.min:
            raise ValueError("max must be >= min")
        return self


def _range(lo: float, hi: float):
    return Field(default_factory=lambda: Range(min=lo, max=hi))


class AppSettings(BaseModel):
    # story
    default_model: str = Field(default_factory=lambda: config.NINEROUTER_MODEL)
    seconds_per_scene: float = Field(default_factory=lambda: config.SECONDS_PER_SCENE, ge=2, le=30)
    # model for "Ubah narasi dengan AI" (short rewrites: a fast, cheap model is enough)
    rewrite_model: str = "gemini/gemini-3.5-flash-lite"
    default_style_id: str = "doodle-stickman"
    default_language: str = "Indonesia"

    # worker pacing (seconds unless noted)
    tempo_preset: Literal["santai", "normal", "cepat", "custom"] = "normal"
    delay_between_images: Range = Field(
        default_factory=lambda: Range(min=config.DELAY_BETWEEN_IMAGES_MIN, max=config.DELAY_BETWEEN_IMAGES_MAX)
    )
    delay_between_redownloads: Range = Field(
        default_factory=lambda: Range(min=config.REDOWNLOAD_DELAY_MIN, max=config.REDOWNLOAD_DELAY_MAX)
    )
    think_before_typing: Range = _range(0, 0)
    char_delay_ms: Range = _range(0, 0)
    before_send: Range = _range(0.3, 0.8)
    typing_mode: Literal["human", "fast"] = "fast"

    # concurrency (simultaneous generate across tabs)
    concurrent_generate: bool = True
    max_concurrency: int = Field(3, ge=1, le=10)

    # breaks & limits (0 = off)
    break_every_images: int = Field(0, ge=0, le=500)
    break_minutes: Range = _range(3, 5)
    session_limit_images: int = Field(0, ge=0, le=1000)

    # download
    resolution: Literal["2K", "1K", "thumbnail"] = "2K"
    download_mode: Literal["batch_end", "immediate"] = "batch_end"

    # Chrome notifications from the extension (project done, session limit, repeated errors)
    notifications: bool = True

    # advanced
    image_timeout_sec: float = Field(240, ge=30, le=1800)


def load() -> AppSettings:
    with _lock:
        if SETTINGS_FILE.exists():
            return AppSettings.model_validate_json(SETTINGS_FILE.read_text(encoding="utf-8"))
        return AppSettings()


def save(settings: AppSettings) -> AppSettings:
    with _lock:
        tmp = SETTINGS_FILE.with_suffix(".json.tmp")
        tmp.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(SETTINGS_FILE)
    return settings
