"""Image job queue. One scene is generated at a time across all projects."""

import base64
import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path

from . import config, settings, storage
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


def _fail_scene(s: Scene, error: str) -> None:
    if s.job_kind == "redownload" and s.image_file:
        # the thumbnail is still there: keep the scene usable
        s.image_status, s.error = "done", f"ambil ulang HD gagal: {error}"[:500]
    else:
        s.image_status, s.error = "failed", error[:500]
    s.job_kind = "generate"


def _expire_stale(project: Project) -> bool:
    changed = False
    cfg = settings.load()
    timeout = min(config.JOB_TIMEOUT_SECONDS, max(60.0, getattr(cfg, "image_timeout_sec", 180.0)))
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
        active = [p for p in storage.list_all() if p.status == "generating"]
        for p in active:
            if _expire_stale(p):
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
        write(d / name)
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
