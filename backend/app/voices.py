"""Voice library for narration audio: one reference recording per voice, cloned by the TTS models.

Each voice lives in VOICES_DIR/<id>/ as ref.wav (mono 48 kHz) + meta.json.
"""

import re
import shutil
import sqlite3
import subprocess
import tempfile
import uuid
import wave
from pathlib import Path

from pydantic import BaseModel

from . import config
from .models import now_iso

MIN_SECONDS, MAX_SECONDS = 1.0, 11.5


class Voice(BaseModel):
    id: str
    name: str
    transcript: str = ""
    duration: float
    created_at: str


def _dir(voice_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", voice_id or ""):
        raise ValueError("invalid voice id")
    return config.VOICES_DIR / voice_id


def ref_path(voice_id: str) -> Path:
    return _dir(voice_id) / "ref.wav"


def wav_duration(path: Path) -> float:
    with wave.open(str(path)) as w:
        return round(w.getnframes() / w.getframerate(), 3)


def get(voice_id: str) -> Voice | None:
    try:
        meta = _dir(voice_id) / "meta.json"
    except ValueError:
        return None
    if not meta.is_file() or not ref_path(voice_id).is_file():
        return None
    return Voice.model_validate_json(meta.read_text(encoding="utf-8"))


def list_voices() -> list[Voice]:
    if not config.VOICES_DIR.exists():
        return []
    found = [get(d.name) for d in config.VOICES_DIR.iterdir() if d.is_dir()]
    return sorted((v for v in found if v), key=lambda v: v.name.lower())


def _save_meta(v: Voice) -> None:
    (_dir(v.id) / "meta.json").write_text(v.model_dump_json(indent=2), encoding="utf-8")


def create(name: str, transcript: str, data: bytes, filename: str) -> Voice:
    """Normalise an uploaded recording to mono 48 kHz WAV and add it to the library."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise ValueError("ffmpeg tidak ditemukan di PATH")
    voice_id = uuid.uuid4().hex
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / f"upload{Path(filename).suffix or '.wav'}"
        src.write_bytes(data)
        out = Path(tmp) / "ref.wav"
        r = subprocess.run([ffmpeg, "-y", "-i", str(src), "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", str(out)],
                           capture_output=True)
        if r.returncode != 0 or not out.is_file():
            raise ValueError(f"rekaman tidak bisa dibaca: {r.stderr.decode(errors='ignore')[-300:]}")
        duration = wav_duration(out)
        if not MIN_SECONDS <= duration <= MAX_SECONDS:
            raise ValueError(f"Durasi rekaman harus 1–11,5 detik (sekarang {duration:.1f} dtk)")
        d = _dir(voice_id)
        d.mkdir(parents=True, exist_ok=True)
        shutil.move(str(out), d / "ref.wav")
    v = Voice(id=voice_id, name=name.strip(), transcript=transcript.strip(), duration=duration, created_at=now_iso())
    _save_meta(v)
    return v


def delete(voice_id: str) -> None:
    if get(voice_id) is None:
        raise LookupError("voice not found")
    shutil.rmtree(_dir(voice_id))


def import_legacy(db_path: Path) -> int:
    """Copy the voice library of manhwa-recap-studio (its studio.db `voices` table) into this app."""
    if not Path(db_path).is_file():
        raise FileNotFoundError(f"database tidak ditemukan: {db_path}")
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT id, nama, transkrip, path_wav, durasi, created_at FROM voices").fetchall()
    finally:
        con.close()
    imported = 0
    for voice_id, name, transcript, path_wav, duration, created_at in rows:
        try:
            d = _dir(voice_id)
        except ValueError:
            continue
        if get(voice_id) is not None or not path_wav or not Path(path_wav).is_file():
            continue
        d.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path_wav, d / "ref.wav")
        _save_meta(Voice(id=voice_id, name=name or "Tanpa nama", transcript=transcript or "",
                         duration=float(duration or wav_duration(d / "ref.wav")), created_at=created_at or now_iso()))
        imported += 1
    return imported
