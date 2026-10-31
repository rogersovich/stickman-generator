"""Narration audio queue: one TTS clip per scene, made by a worker-tts process (Mac or a remote PC).

Scene status lives in project.json; leases (which worker holds which scene) live in memory only,
so a backend restart puts every generating scene back in the queue (reset_on_startup).
"""

import hashlib
import io
import random
import re
import time
import wave
from typing import Literal

from . import config, settings, storage, voices
from .models import Project, Scene, TtsModel, now_iso

LANG_CODES = {"indonesia": "id", "english": "en"}

_leases: dict[tuple[str, int], tuple[str, float]] = {}  # (project_id, scene index) -> (worker name, expires at)
_workers: dict[str, dict] = {}  # worker name -> {"models", "device", "local", "seen"}


def _reset_registry() -> None:
    _leases.clear()
    _workers.clear()


def lang_code(language: str) -> str:
    return LANG_CODES.get((language or "").strip().lower(), "id")


def resolve(p: Project) -> tuple[str | None, TtsModel]:
    cfg = settings.load()
    return p.voice_id or cfg.tts_voice_id, p.tts_model or cfg.tts_model


def audio_key(narration: str, voice_id: str | None, model: str, speed: float = 1.0) -> str:
    speed_tag = f"\n{round(speed, 2)}" if abs(speed - 1.0) > 0.01 else ""
    return hashlib.sha1(f"{model}\n{voice_id}{speed_tag}\n{narration.strip()}".encode()).hexdigest()[:16]


def is_stale(p: Project, s: Scene) -> bool:
    voice_id, model = resolve(p)
    speed = voices.get_voice_speed(voice_id) if voice_id else 1.0
    return s.audio_status == "done" and s.audio_key != audio_key(s.narration, voice_id, model, speed)


def _load(project_id: str) -> Project:
    p = storage.load(project_id)
    if p is None:
        raise LookupError("project not found")
    return p


END_PUNCT_REGEX = re.compile(r"[\.\!\?\u2026]+[\"\'\u201d\u2019]?\s*$")


def get_sentence_groups(scenes: list[Scene], max_scenes: int = 4, max_words: int = 35) -> list[list[int]]:
    groups: list[list[int]] = []
    current_group: list[int] = []
    current_words = 0

    for i, s in enumerate(scenes):
        narration = (s.narration or "").strip()
        words = len(narration.split())
        current_group.append(i)
        current_words += words

        ends_sentence = bool(END_PUNCT_REGEX.search(narration))
        reached_limit = len(current_group) >= max_scenes or current_words >= max_words

        if ends_sentence or reached_limit or i == len(scenes) - 1:
            groups.append(current_group)
            current_group = []
            current_words = 0

    return groups


def get_scene_group_map(scenes: list[Scene]) -> dict[int, list[int]]:
    groups = get_sentence_groups(scenes)
    mapping: dict[int, list[int]] = {}
    for g in groups:
        for idx in g:
            mapping[idx] = g
    return mapping


def enqueue(project_id: str, mode: Literal["missing", "all"], indices: list[int] | None = None) -> Project:
    with storage.lock:
        p = _load(project_id)
        if p.status == "draft":
            raise ValueError("Project masih draft")
        voice_id, _ = resolve(p)
        if not voice_id:
            raise ValueError("Pilih suara dulu")
        if voices.get(voice_id) is None:
            raise ValueError("Suara tidak ditemukan")

        group_map = get_scene_group_map(p.scenes)
        if indices is None:
            targets = list(range(len(p.scenes)))
        else:
            expanded = set()
            for i in indices:
                if 0 <= i < len(p.scenes):
                    expanded.update(group_map.get(i, [i]))
            targets = sorted(expanded)

        for i in targets:
            s = p.scenes[i]
            if s.audio_status == "generating":
                continue
            if not s.narration.strip():
                s.audio_status, s.audio_error = "failed", "Narasi kosong"
                continue
            if mode == "all" or s.audio_status in ("pending", "failed") or is_stale(p, s):
                s.audio_status, s.audio_error = "queued", None

        # Ensure all members of affected sentence groups are queued together
        queued_indices = {i for i, s in enumerate(p.scenes) if s.audio_status == "queued"}
        for q_idx in list(queued_indices):
            for m in group_map.get(q_idx, [q_idx]):
                m_scene = p.scenes[m]
                if m_scene.audio_status != "generating" and m_scene.narration.strip():
                    m_scene.audio_status, m_scene.audio_error = "queued", None

        storage.save(p)
        return p


def cancel(project_id: str, indices: list[int] | None = None) -> Project:
    with storage.lock:
        p = _load(project_id)
        group_map = get_scene_group_map(p.scenes)
        if indices is None:
            targets = list(range(len(p.scenes)))
        else:
            expanded = set()
            for i in indices:
                if 0 <= i < len(p.scenes):
                    expanded.update(group_map.get(i, [i]))
            targets = sorted(expanded)

        for i in targets:
            s = p.scenes[i]
            if s.audio_status in ("queued", "generating"):
                s.audio_status = "done" if s.audio_file and not is_stale(p, s) else "pending"
                s.audio_error = None
            _leases.pop((project_id, i), None)
        storage.save(p)
        return p


def pause(project_id: str) -> Project:
    return cancel(project_id)


def heartbeat(name: str, models: list[str], device: str, is_local: bool) -> None:
    with storage.lock:
        now = time.time()
        _workers[name] = {"models": list(models), "device": device, "local": is_local, "seen": now}
        for key, (holder, _) in list(_leases.items()):
            if holder == name:
                _leases[key] = (holder, now + config.TTS_LEASE_SECONDS)


def workers_status() -> list[dict]:
    now = time.time()
    return [
        {"name": n, "device": w["device"], "models": w["models"], "local": w["local"],
         "online": now - w["seen"] <= config.TTS_SEEN_SECONDS}
        for n, w in sorted(_workers.items())
    ]


def _allowed_models(models: list[str], is_local: bool, worker_device: str = "") -> set[str]:
    allowed = set(models)
    if is_local and config.TTS_WORKER_MODE == "remote":
        return set()
    if is_local and config.TTS_WORKER_MODE == "auto":
        for w in workers_status():
            if w["online"] and not w["local"] and "cuda" in w.get("device", "").lower():
                allowed -= set(w["models"])
    if not is_local and config.TTS_WORKER_MODE == "auto" and "cuda" not in worker_device.lower():
        for w in workers_status():
            if w["online"] and w["local"] and "cuda" in w.get("device", "").lower():
                return set()
    return allowed


def claim(name: str, models: list[str], is_local: bool) -> dict | None:
    with storage.lock:
        reap()
        heartbeat(name, models, _workers.get(name, {}).get("device", ""), is_local)
        allowed = _allowed_models(models, is_local, _workers.get(name, {}).get("device", ""))
        if not allowed:
            return None
        for p in sorted(storage.list_all(), key=lambda p: p.created_at):
            if p.status == "draft" or not any(s.audio_status == "queued" for s in p.scenes):
                continue
            voice_id, model = resolve(p)
            if model not in allowed:
                continue
            voice = voices.get(voice_id) if voice_id else None
            if voice is None:
                for s in p.scenes:
                    if s.audio_status == "queued":
                        s.audio_status, s.audio_error = "failed", "Suara tidak ditemukan"
                storage.save(p)
                continue
            first_q = next(i for i, s in enumerate(p.scenes) if s.audio_status == "queued")
            group_map = get_scene_group_map(p.scenes)
            group = group_map.get(first_q, [first_q])

            seed = random.randint(1, 2**31 - 1)
            for idx in group:
                s_member = p.scenes[idx]
                s_member.audio_status, s_member.audio_error, s_member.audio_seed = "generating", None, seed
                s_member.audio_started_at, s_member.audio_worker = now_iso(), name
                _leases[(p.id, idx)] = (name, time.time() + config.TTS_LEASE_SECONDS)
            storage.save(p)

            params = getattr(settings.load(), model).model_dump()
            voice_speed = voices.get_voice_speed(voice.id)
            params["speed"] = voice_speed
            v_cfg = voices.VOICE_REGISTRY.get(voice.id)
            lora_path = getattr(v_cfg, "lora_path", None) if v_cfg else None
            lora_scale = getattr(v_cfg, "lora_scale", None) if v_cfg else None

            scene_texts = [p.scenes[idx].narration.strip() for idx in group]
            scene_keys = [audio_key(p.scenes[idx].narration, voice_id, model, voice_speed) for idx in group]
            combined_text = " ".join(t for t in scene_texts if t)

            return {
                "project_id": p.id,
                "scene_indices": group,
                "scene_index": group[0],
                "scene_texts": scene_texts,
                "scene_keys": scene_keys,
                "text": combined_text,
                "lang": lang_code(p.language),
                "voice_id": voice.id,
                "voice_version": int(voices.ref_path(voice.id).stat().st_mtime),
                "voice_transcript": voice.transcript,
                "model": model,
                "params": params,
                "speed": voice_speed,
                "seed": seed,
                "key": audio_key(combined_text, voice_id, model, voice_speed),
                "lora_path": lora_path,
                "lora_scale": lora_scale,
            }
        return None


def _take_lease(project_id: str, index: int, name: str) -> None:
    holder = _leases.get((project_id, index))
    if holder is None or holder[0] != name:
        raise PermissionError("scene is no longer assigned to this worker")
    del _leases[(project_id, index)]


def concat_wav_files(files: list, out_file) -> None:
    if not files:
        return
    import wave
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(files[0]), 'rb') as w0:
        params = w0.getparams()
    with wave.open(str(out_file), 'wb') as out_w:
        out_w.setparams(params)
        for f in files:
            with wave.open(str(f), 'rb') as in_w:
                out_w.writeframes(in_w.readframes(in_w.getnframes()))


def save_group_result(project_id: str, index: int, name: str, key: str, data: bytes) -> Project:
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("not a WAV file")
    with storage.lock:
        p = _load(project_id)
        d = storage.project_dir(project_id) / "audio"
        d.mkdir(parents=True, exist_ok=True)
        name_ = f"scene_{index + 1:03d}_group.wav"
        dest_file = d / name_
        dest_file.write_bytes(data)
        if config.has_r2():
            try:
                from . import r2
                r2.upload_file(dest_file, f"projects/{project_id}/audio/{name_}", "audio/wav")
            except Exception:
                pass
        return p


def save_result(project_id: str, index: int, name: str, key: str, data: bytes, audit_data: dict | None = None) -> Project:
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("not a WAV file")
    try:
        with wave.open(io.BytesIO(data)) as w:
            duration = round(w.getnframes() / w.getframerate(), 3)
    except (wave.Error, EOFError, ZeroDivisionError) as e:
        raise ValueError(f"invalid WAV: {e}") from e
    with storage.lock:
        p = _load(project_id)
        if not 0 <= index < len(p.scenes):
            raise LookupError("scene not found")
        _take_lease(project_id, index, name)
        d = storage.project_dir(project_id) / "audio"
        d.mkdir(parents=True, exist_ok=True)
        name_ = f"scene_{index + 1:03d}.wav"
        dest_file = d / name_
        dest_file.write_bytes(data)
        if config.has_r2():
            try:
                from . import r2
                r2.upload_file(dest_file, f"projects/{project_id}/audio/{name_}", "audio/wav")
            except Exception:
                pass
        s = p.scenes[index]
        s.audio_status, s.audio_file, s.audio_duration = "done", f"audio/{name_}", duration
        s.audio_key, s.audio_error = key, None
        if audit_data:
            s.audio_audit_score = audit_data.get("score")
            s.audio_audit_status = audit_data.get("status")
            s.audio_audit_text = audit_data.get("transcribed")
            s.audio_audit_issues = audit_data.get("issues", [])
        storage.save(p)
        return p


def fail(project_id: str, index: int, name: str, error: str) -> Project:
    with storage.lock:
        p = _load(project_id)
        if not 0 <= index < len(p.scenes):
            raise LookupError("scene not found")
        _take_lease(project_id, index, name)
        s = p.scenes[index]
        s.audio_status, s.audio_error = "failed", (error or "unknown error")[:500]
        storage.save(p)
        return p


def reap() -> int:
    """Put scenes whose worker went silent back in the queue."""
    with storage.lock:
        now = time.time()
        expired = [key for key, (_, until) in _leases.items() if until < now]
        for project_id, index in expired:
            del _leases[(project_id, index)]
            p = storage.load(project_id)
            if p and 0 <= index < len(p.scenes) and p.scenes[index].audio_status == "generating":
                p.scenes[index].audio_status = "queued"
                storage.save(p)
        return len(expired)


def reset_on_startup() -> int:
    """Leases are lost on restart: every generating scene goes back to the queue."""
    count = 0
    with storage.lock:
        for p in storage.list_all():
            changed = [s for s in p.scenes if s.audio_status == "generating"]
            for s in changed:
                s.audio_status = "queued"
            if changed:
                storage.save(p)
                count += len(changed)
    return count
