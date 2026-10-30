"""Sound-effect library for the CapCut export: built-in clips plus custom uploads, each with a volume.

Built-in clips ship in backend/assets/sfx/<id>.wav (same set as manhwa-recap-studio's short maker).
Custom uploads and per-clip label/volume overrides live in SFX_DIR (meta.json + sfx_<hex>.wav).
"""

import json
import re
import shutil
import subprocess
import tempfile
import time
import uuid
import wave
from pathlib import Path

from . import config

BUILTIN_DIR = config.BACKEND_DIR / "assets" / "sfx"
MAX_SECONDS = 30.0
DEFAULT_VOLUME = 0.3

# id, label, description, category, default volume (tuned in manhwa-recap-studio)
BUILTINS: list[tuple[str, str, str, str, float]] = [
    ("whoosh", "Whoosh 1", "Transisi cepat pergerakan panel.", "transition", 0.3),
    ("whoosh_2", "Whoosh 2", "Transisi cepat pergerakan panel (variasi).", "transition", 0.3),
    ("spawn", "Spawn", "Efek kemunculan karakter atau item.", "transition", 0.3),
    ("camera_flash", "Camera Flash", "Jepretan kamera atau blitz foto.", "transition", 0.3),
    ("dbz_teleport", "DBZ Teleportation", "Teleportasi instan ala Dragon Ball Z.", "transition", 0.3),
    ("shine_anime", "Shine Anime", "Kilau atau aura menyala ala anime.", "reaction", 0.3),
    ("awkward_moment", "Awkward Moment", "Momen canggung atau kebingungan.", "reaction", 0.3),
    ("awkward_pause_1", "Awkward Pause 1", "Jeda hening canggung.", "reaction", 0.5),
    ("awkward_pause_2", "Awkward Pause 2", "Jeda hening canggung (variasi).", "reaction", 0.3),
    ("rizz_sound", "Rizz Sound", "Pesona tatapan maut karismatik.", "reaction", 0.3),
    ("eye_wink", "Eye Wink", "Kedipan mata atau ting manis.", "reaction", 0.3),
    ("taco_bell", "Taco Bell Bong", "Dentang kaget atau plot twist kocak.", "reaction", 0.25),
    ("breast_twitch", "Twitch Sound", "Gerakan kedut cepat.", "reaction", 0.3),
    ("fahh", "Fahh / Sigh", "Desah kaget, heran, atau kagum.", "reaction", 0.25),
    ("munch_bite", "Munch Bite", "Gigitan renyah makanan.", "reaction", 0.3),
    ("sword_3", "Sword 3", "Denting sabetan pedang tajam.", "action", 0.3),
    ("sword_4", "Sword 4", "Sabetan bilah pedang cepat.", "action", 0.3),
    ("sword_5", "Sword 5", "Benturan keras bentrokan pedang.", "action", 0.3),
    ("katana_reverb", "Katana Reverb", "Hunus katana bergema.", "action", 0.3),
    ("anime_3", "Anime Action 3", "Efek aksi dinamis anime.", "action", 0.3),
    ("bone_crack", "Bone Crack", "Retakan tulang atau patah keras.", "action", 0.3),
    ("punch_anime", "Punch Anime", "Pukulan telak tinju anime.", "action", 0.25),
    ("anime_5", "Anime Dramatic 5", "Efek dramatis tensi tinggi.", "dramatic", 0.25),
    ("bonk", "Bonk Sound", "Pukulan komedi bonk di kepala.", "impact", 0.8),
    ("glass_breaking", "Glass Breaking", "Pecahan kaca dramatis.", "impact", 0.3),
    ("bamboo_hit", "Bamboo Hit", "Hantaman keras kayu bambu.", "impact", 1.0),
]
_BUILTIN = {b[0]: b for b in BUILTINS}
_CUSTOM_ID = re.compile(r"sfx_[a-f0-9]{12}")


def _meta_file() -> Path:
    return config.SFX_DIR / "meta.json"


def _read_meta() -> dict:
    f = _meta_file()
    meta = {}
    if f.is_file():
        try:
            meta = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            meta = {}
    meta.setdefault("custom", [])
    meta.setdefault("volumes", {})
    meta.setdefault("labels", {})
    return meta


def _write_meta(meta: dict) -> None:
    config.SFX_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _meta_file().with_suffix(".tmp")
    tmp.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(_meta_file())


def path(sfx_id: str) -> Path:
    if sfx_id in _BUILTIN:
        return BUILTIN_DIR / f"{sfx_id}.wav"
    if _CUSTOM_ID.fullmatch(sfx_id or ""):
        return config.SFX_DIR / f"{sfx_id}.wav"
    raise LookupError("SFX tidak ditemukan")


def duration(sfx_id: str) -> float:
    try:
        with wave.open(str(path(sfx_id))) as w:
            return round(w.getnframes() / w.getframerate(), 3)
    except (LookupError, OSError, wave.Error, ZeroDivisionError):
        return 0.0


def _entry(sfx_id: str, meta: dict) -> dict | None:
    if sfx_id in _BUILTIN:
        _, label, desc, category, vol = _BUILTIN[sfx_id]
        item = {"id": sfx_id, "label": label, "desc": desc, "category": category, "built_in": True, "volume": vol}
    else:
        custom = next((c for c in meta["custom"] if c.get("id") == sfx_id), None)
        if custom is None:
            return None
        item = {"id": sfx_id, "label": custom["label"], "desc": custom.get("desc", ""), "category": "custom",
                "built_in": False, "volume": custom.get("volume", DEFAULT_VOLUME)}
    if not path(sfx_id).is_file():
        return None
    item["label"] = meta["labels"].get(sfx_id, item["label"])
    item["volume"] = float(meta["volumes"].get(sfx_id, item["volume"]))
    item["duration"] = duration(sfx_id)
    return item


def get(sfx_id: str) -> dict | None:
    try:
        return _entry(sfx_id, _read_meta())
    except LookupError:
        return None


def list_catalog() -> list[dict]:
    meta = _read_meta()
    ids = [c.get("id", "") for c in meta["custom"]] + [b[0] for b in BUILTINS]
    out = []
    for sfx_id in ids:
        try:
            item = _entry(sfx_id, meta)
        except LookupError:
            continue
        if item:
            out.append(item)
    return out


def volume(sfx_id: str) -> float:
    item = get(sfx_id)
    return item["volume"] if item else DEFAULT_VOLUME


def update(sfx_id: str, label: str | None = None, volume: float | None = None) -> dict:
    if get(sfx_id) is None:
        raise LookupError("SFX tidak ditemukan")
    meta = _read_meta()
    if volume is not None:
        meta["volumes"][sfx_id] = round(max(0.0, min(1.0, float(volume))), 3)
    if label is not None and label.strip():
        meta["labels"][sfx_id] = label.strip()[:60]
    _write_meta(meta)
    return _entry(sfx_id, meta)


def add_custom(data: bytes, filename: str, volume: float = 0.85) -> dict:
    """Convert an uploaded clip to 44.1 kHz 16-bit WAV and add it to the library."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise ValueError("ffmpeg tidak ditemukan di PATH")
    sfx_id = f"sfx_{uuid.uuid4().hex[:12]}"
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / f"upload{Path(filename).suffix or '.wav'}"
        src.write_bytes(data)
        out = Path(tmp) / "out.wav"
        r = subprocess.run([ffmpeg, "-y", "-i", str(src), "-ar", "44100", "-c:a", "pcm_s16le", str(out)],
                           capture_output=True)
        if r.returncode != 0 or not out.is_file():
            raise ValueError(f"file audio tidak bisa dibaca: {r.stderr.decode(errors='ignore')[-300:]}")
        with wave.open(str(out)) as w:
            secs = w.getnframes() / w.getframerate()
        if secs < 0.05:
            raise ValueError("Audio terlalu pendek untuk SFX")
        if secs > MAX_SECONDS:
            raise ValueError(f"SFX maksimal 30 detik (sekarang {secs:.1f} dtk)")
        config.SFX_DIR.mkdir(parents=True, exist_ok=True)
        shutil.move(str(out), path(sfx_id))
    label = re.sub(r"^\[[^\]]*\]\s*", "", Path(filename).stem).strip() or Path(filename).stem or "SFX"
    meta = _read_meta()
    meta["custom"].insert(0, {"id": sfx_id, "label": label[:60], "desc": f"Upload ({Path(filename).suffix.lstrip('.').upper() or 'WAV'})",
                              "volume": round(max(0.0, min(1.0, volume)), 3), "created": int(time.time())})
    _write_meta(meta)
    return _entry(sfx_id, meta)


def delete_custom(sfx_id: str) -> None:
    if sfx_id in _BUILTIN:
        raise ValueError("SFX bawaan tidak bisa dihapus")
    meta = _read_meta()
    if not any(c.get("id") == sfx_id for c in meta["custom"]):
        raise LookupError("SFX tidak ditemukan")
    meta["custom"] = [c for c in meta["custom"] if c.get("id") != sfx_id]
    meta["volumes"].pop(sfx_id, None)
    meta["labels"].pop(sfx_id, None)
    _write_meta(meta)
    path(sfx_id).unlink(missing_ok=True)
