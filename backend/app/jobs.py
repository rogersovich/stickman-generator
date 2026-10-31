"""Image job queue. One scene is generated at a time across all projects."""

import base64
import hashlib
import shutil
import struct
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from . import config, db, r2, settings, storage
from .models import Project, Scene, now_iso
from .styles import build_prompt

EXT = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


def _age_seconds(iso: str | None) -> float:
    if not iso:
        return 0
    return (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds()


LOW_RES_MAX_BYTES = 300_000  # thumbnails are ~20-40 KB, 2K downloads ~2 MB


def needs_hd(project_id: str, scene: Scene) -> bool:
    """True when the saved image is (probably) only the low-res thumbnail."""
    if scene.image_status != "done" or not scene.image_file or scene.image_hd:
        return False
    if scene.image_hd is False:
        return True
    f = storage.project_dir(project_id) / scene.image_file
    return f.exists() and f.stat().st_size < LOW_RES_MAX_BYTES


@lru_cache(maxsize=4096)
def _image_size(path: str, _mtime_ns: int) -> tuple[int, int] | None:
    """(width, height) read from a PNG / JPEG / WebP header; mtime is part of the cache key."""
    with open(path, "rb") as f:
        head = f.read(64 * 1024)
    if head.startswith(b"\x89PNG") and len(head) >= 24:
        return struct.unpack(">II", head[16:24])
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        if head[12:16] == b"VP8X":
            return 1 + int.from_bytes(head[24:27], "little"), 1 + int.from_bytes(head[27:30], "little")
        if head[12:16] == b"VP8 ":
            w, h = struct.unpack("<HH", head[26:30])
            return w & 0x3FFF, h & 0x3FFF
        if head[12:16] == b"VP8L":
            bits = int.from_bytes(head[21:25], "little")
            return 1 + (bits & 0x3FFF), 1 + ((bits >> 14) & 0x3FFF)
    if head.startswith(b"\xff\xd8"):
        i = 2
        while i + 9 < len(head):
            if head[i] != 0xFF:
                i += 1
                continue
            marker = head[i + 1]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7 or marker == 0xFF:
                i += 2 if marker != 0xFF else 1
                continue
            length = struct.unpack(">H", head[i + 2 : i + 4])[0]
            # SOF0..SOF15 hold the frame size (C4 = DHT, C8 = JPG, CC = DAC are not frames)
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                h, w = struct.unpack(">HH", head[i + 5 : i + 9])
                return w, h
            i += 2 + length
    return None


def image_res(project_id: str, scene: Scene) -> str | None:
    """Label of the saved image's real size: "thumbnail", "1K" or "2K" (Flow 1K = 1376 px long side)."""
    if not scene.image_file:
        return None
    f = storage.project_dir(project_id) / scene.image_file
    try:
        size = _image_size(str(f), f.stat().st_mtime_ns)
    except OSError:
        return None
    if not size:
        return None
    long_side = max(size)
    return "2K" if long_side >= 2000 else "1K" if long_side >= 1000 else "thumbnail"


def _fail_scene(s: Scene, error: str) -> None:
    if s.job_kind == "redownload" and s.image_file:
        # the thumbnail is still there: keep the scene usable
        s.image_status, s.error = "done", f"ambil ulang HD gagal: {error}"[:500]
    else:
        s.image_status, s.error = "failed", error[:500]
        s.failed_at = now_iso()
    s.job_kind = "generate"


def auto_retry_stale_failed(project: Project) -> bool:
    """Auto-retry scenes that failed at least auto_retry_delay_sec ago (default 60s)."""
    cfg = settings.load()
    if not getattr(cfg, "auto_retry_failed_images", True):
        return False
    delay = getattr(cfg, "auto_retry_delay_sec", config.AUTO_RETRY_DELAY_SECONDS) or config.AUTO_RETRY_DELAY_SECONDS
    max_retries = getattr(cfg, "max_auto_retries", config.MAX_AUTO_RETRIES) or config.MAX_AUTO_RETRIES
    changed = False

    for s in project.scenes:
        if getattr(s, "is_merged", False):
            continue
        if s.image_status == "failed" and getattr(s, "auto_retry_count", 0) < max_retries:
            failed_age = _age_seconds(s.failed_at)
            if failed_age >= delay:
                s.image_status = "pending"
                s.error = None
                s.started_at = None
                s.job_kind = "generate"
                s.auto_retry_count = getattr(s, "auto_retry_count", 0) + 1
                s.failed_at = None
                changed = True

    if changed and project.status == "done":
        project.status = "generating"

    return changed


def expire_stale(project: Project) -> bool:
    changed = False
    cfg = settings.load()
    timeout = getattr(cfg, "image_timeout_sec", config.JOB_TIMEOUT_SECONDS) or config.JOB_TIMEOUT_SECONDS
    for s in project.scenes:
        if s.image_status == "generating" and _age_seconds(s.started_at) > timeout:
            _fail_scene(s, "timeout: no result from extension")
            changed = True
    return changed


def _refresh_status(project: Project) -> None:
    # Sync status for any merged scenes whose target scene finished
    for other in project.scenes:
        if getattr(other, "is_merged", False) and other.merged_with is not None:
            if 0 <= other.merged_with < len(project.scenes):
                parent = project.scenes[other.merged_with]
                if parent.image_status in ("done", "failed"):
                    other.image_status = parent.image_status
                    other.image_file = parent.image_file
                    other.image_hd = parent.image_hd
                    other.flow_src = getattr(parent, "flow_src", None)
                    other.error = parent.error

    if project.status == "generating" and all(s.image_status in ("done", "failed") for s in project.scenes):
        project.status = "done"


def next_job() -> dict | None:
    with storage.lock:
        all_projects = storage.list_all()
        cfg = settings.load()
        max_retries = getattr(cfg, "max_auto_retries", config.MAX_AUTO_RETRIES) or config.MAX_AUTO_RETRIES
        auto_retry = getattr(cfg, "auto_retry_failed_images", True)

        active = []
        for p in all_projects:
            if p.status == "generating":
                active.append(p)
            elif p.status == "done" and auto_retry:
                has_retryable = any(
                    s.image_status == "failed"
                    and not getattr(s, "is_merged", False)
                    and getattr(s, "auto_retry_count", 0) < max_retries
                    for s in p.scenes
                )
                if has_retryable:
                    active.append(p)

        for p in active:
            stale = expire_stale(p)
            retried = auto_retry_stale_failed(p)
            if stale or retried:
                _refresh_status(p)
                storage.save(p)
        cfg = settings.load()
        max_concurrency = cfg.max_concurrency if getattr(cfg, "concurrent_generate", True) else 1
        generating_count = sum(1 for p in active for s in p.scenes if s.image_status == "generating")
        if generating_count >= max_concurrency:
            return None
        for p in sorted(active, key=lambda p: p.created_at):
            for i, s in enumerate(p.scenes):
                # Skip merged scenes because they reuse parent scene's image
                if getattr(s, "is_merged", False):
                    continue
                if s.image_status == "pending":
                    s.image_status, s.error, s.started_at = "generating", None, now_iso()
                    if getattr(p, "test_limit", None) is not None:
                        p.test_limit -= 1
                        if p.test_limit <= 0:
                            p.status = "paused"
                            p.test_limit = None
                    storage.save(p)
                    job = {
                        "project_id": p.id,
                        "project_title": p.title,
                        "scene_index": i,
                        "total": len(p.scenes),
                        "kind": s.job_kind,
                    }
                    if s.job_kind == "redownload":
                        data = (storage.project_dir(p.id) / s.image_file).read_bytes() if s.image_file else b""
                        job |= {
                            "thumb_sha256": hashlib.sha256(data).hexdigest() if data else "",
                            "flow_src": getattr(s, "flow_src", None),
                            "delay_min": cfg.delay_between_redownloads.min,
                            "delay_max": cfg.delay_between_redownloads.max,
                        }
                    else:
                        job |= {
                            "prompt": build_prompt(p, s),
                            "delay_min": cfg.delay_between_images.min,
                            "delay_max": cfg.delay_between_images.max,
                        }
                    return job
            _refresh_status(p)
            storage.save(p)
        return None


def _get_scene_project(project_id: str, index: int) -> Project:
    p = storage.load(project_id)
    if p is None:
        raise LookupError("project not found")
    if not 0 <= index < len(p.scenes):
        raise LookupError(f"scene {index} not found in project {project_id}")
    return p


def _store(project_id: str, index: int, ext: str, write, note: str | None, hd: bool, flow_src: str | None = None) -> Project:
    with storage.lock:
        p = _get_scene_project(project_id, index)
        d = storage.project_dir(project_id)
        for old in d.glob(f"scene_{index + 1:03d}.*"):  # drop a previous version with another extension
            old.unlink()
        name = f"scene_{index + 1:03d}.{ext}"
        target_path = d / name
        write(target_path)
        if config.has_r2():
            try:
                r2.upload_file(target_path, f"projects/{project_id}/{name}")
            except Exception:
                pass
        s = p.scenes[index]
        s.image_status, s.image_file, s.error, s.image_hd, s.job_kind = "done", name, note, hd, "generate"
        if flow_src:
            s.flow_src = flow_src

        # Auto-link image to any merged scenes referencing this scene
        for other in p.scenes:
            if getattr(other, "is_merged", False) and getattr(other, "merged_with", None) == index:
                other.image_status, other.image_file, other.error, other.image_hd, other.job_kind = "done", name, note, hd, "generate"
                if flow_src:
                    other.flow_src = flow_src

        _refresh_status(p)
        storage.save(p)
        return p


def save_result(project_id: str, index: int, image_base64: str, mime: str, note: str | None = None, flow_src: str | None = None, hd: bool = False) -> Project:
    if "," in image_base64[:100]:  # strip "data:image/png;base64," prefix
        image_base64 = image_base64.split(",", 1)[1]
    data = base64.b64decode(image_base64)
    cfg = settings.load()
    is_hd = hd or (cfg.resolution == "1K" and len(data) > 100_000)
    try:
        db.save_snapshot_record(project_id, index, data, mime, flow_src=flow_src, note=note)
    except Exception:
        pass
    return _store(project_id, index, EXT.get(mime, "png"), lambda f: f.write_bytes(data), note, hd=is_hd, flow_src=flow_src)


def save_result_file(project_id: str, index: int, path: str, note: str | None = None) -> Project:
    """Move a file Chrome downloaded (full resolution) into the project folder."""
    src = Path(path).resolve()
    if not src.is_relative_to(config.DOWNLOADS_DIR):
        raise PermissionError(f"file must be inside {config.DOWNLOADS_DIR}")
    if not src.is_file():
        raise FileNotFoundError(f"downloaded file not found: {src}")
    ext = src.suffix.lstrip(".").lower() or "png"
    if ext not in ("png", "jpg", "jpeg", "webp"):
        raise ValueError(f"not an image: {src.name}")
    try:
        db.save_snapshot_record(project_id, index, src.read_bytes(), f"image/{ext}", note=note)
    except Exception:
        pass
    return _store(project_id, index, ext, lambda f: shutil.move(src, f), note, hd=True)


def mark_failed(project_id: str, index: int, error: str) -> Project:
    with storage.lock:
        p = _get_scene_project(project_id, index)
        _fail_scene(p.scenes[index], error)
        for other in p.scenes:
            if getattr(other, "is_merged", False) and getattr(other, "merged_with", None) == index:
                _fail_scene(other, f"scene induk {index + 1} gagal: {error}")
        _refresh_status(p)
        storage.save(p)
        return p


def release(project_id: str, index: int) -> Project:
    """Put a scene that was being generated back in the queue (worker stopped mid-job)."""
    with storage.lock:
        p = _get_scene_project(project_id, index)
        s = p.scenes[index]
        if s.image_status == "generating":
            s.image_status, s.started_at = "pending", None
            storage.save(p)
        return p


def request_redownload(project_id: str, indices: list[int] | None = None) -> Project:
    """Queue full-res re-downloads of existing Flow images (no new generation)."""
    with storage.lock:
        p = storage.load(project_id)
        if p is None:
            raise LookupError("project not found")
        targets = range(len(p.scenes)) if indices is None else indices
        queued = 0
        for i in targets:
            if 0 <= i < len(p.scenes):
                s = p.scenes[i]
                if s.image_status == "done" and s.image_file and (indices is not None or needs_hd(project_id, s)):
                    s.image_status, s.job_kind, s.error = "pending", "redownload", None
                    queued += 1
        if queued > 0:
            if p.status == "done":
                p.status = "generating"
            storage.save(p)
        return p


def clear_images(project_id: str) -> Project:
    """Delete all generated image files for a project, clear SQLite snapshots, and reset scenes to fresh pending state."""
    with storage.lock:
        p = storage.load(project_id)
        if p is None:
            raise LookupError("project not found")
        d = storage.project_dir(project_id)
        for pattern in ("scene_*.*", "*.png", "*.jpg", "*.jpeg", "*.webp"):
            for f in d.glob(pattern):
                if f.is_file():
                    try:
                        f.unlink()
                    except Exception:
                        pass
        dl_dir = config.DOWNLOADS_DIR / "stickman-flow" / project_id
        if dl_dir.exists():
            shutil.rmtree(dl_dir, ignore_errors=True)
        for s in p.scenes:
            s.image_status = "pending"
            s.image_file = None
            s.flow_src = None
            s.error = None
            s.started_at = None
            s.failed_at = None
            s.auto_retry_count = 0
            s.image_hd = None
            s.job_kind = "generate"
        p.status = "paused"
        p.test_limit = None
        _refresh_status(p)
        storage.save(p)
        try:
            db.clear_project_snapshots(project_id)
        except Exception:
            pass
        return p


def set_test_run(project_id: str, limit: int = 2) -> Project:
    """Set project into test run mode: generates at most `limit` scenes then auto-pauses."""
    with storage.lock:
        p = storage.load(project_id)
        if p is None:
            raise LookupError("project not found")
        p.test_limit = max(1, limit)
        p.status = "generating"
        storage.save(p)
        return p
