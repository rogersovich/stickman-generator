import concurrent.futures
import logging
import re
import shutil
import threading
import time
from pathlib import Path

from . import config, d1, db, r2
from .models import Project, now_iso

logger = logging.getLogger("storage")
lock = threading.RLock()
_cloud_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="cloud_sync")


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:40] or "project"


def new_project_id(topic: str) -> str:
    return f"{slugify(topic)}-{time.strftime('%Y%m%d-%H%M%S')}"


def project_dir(project_id: str) -> Path:
    if not re.fullmatch(r"[a-z0-9-]+", project_id):
        raise ValueError("invalid project id")
    return config.OUTPUT_DIR / project_id


def _sync_to_cloud_bg(project: Project, project_file: Path) -> None:
    """Sync project to Cloudflare D1 and R2 in the background."""
    if config.has_d1():
        try:
            d1.save_project(project)
        except Exception as e:
            logger.error(f"Failed to sync project to D1: {e}")

    if config.has_r2() and project_file.exists():
        try:
            r2.upload_file(project_file, f"projects/{project.id}/project.json", "application/json")
        except Exception as e:
            logger.error(f"Failed to sync project metadata to R2: {e}")


def _delete_from_cloud_bg(project_id: str) -> None:
    """Delete project from Cloudflare D1 and R2 in the background."""
    if config.has_d1():
        try:
            d1.delete_project(project_id)
        except Exception as e:
            logger.error(f"Failed to delete project from D1: {e}")

    if config.has_r2():
        try:
            r2.delete_prefix(f"projects/{project_id}/")
        except Exception as e:
            logger.error(f"Failed to delete assets from R2: {e}")


def save(project: Project) -> None:
    with lock:
        d = project_dir(project.id)
        d.mkdir(parents=True, exist_ok=True)
        project.updated_at = now_iso()
        project_file = d / "project.json"
        tmp = d / "project.json.tmp"
        tmp.write_text(project.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(project_file)

        # 1. Sync to local SQLite
        try:
            db.save_project_record(project)
        except Exception:
            pass

    # 2. Async sync to Cloudflare D1 and R2 without blocking the main event loop
    if config.has_d1() or config.has_r2():
        _cloud_executor.submit(_sync_to_cloud_bg, project, project_file)


def load(project_id: str) -> Project | None:
    with lock:
        d = project_dir(project_id)
        f = d / "project.json"

        # 1. Local disk adalah primary fast cache (0.05 ms)
        if f.exists():
            try:
                return Project.model_validate_json(f.read_text(encoding="utf-8"))
            except Exception:
                pass

        # 2. Fallback: jika belum ada di lokal, coba unduh dari Cloudflare D1
        if config.has_d1():
            try:
                remote_proj = d1.load_project(project_id)
                if remote_proj:
                    d.mkdir(parents=True, exist_ok=True)
                    f.write_text(remote_proj.model_dump_json(indent=2), encoding="utf-8")
                    return remote_proj
            except Exception as e:
                logger.error(f"Failed to load from D1: {e}")

        # 3. Fallback: coba unduh dari Cloudflare R2
        if config.has_r2():
            try:
                if r2.download_file(f"projects/{project_id}/project.json", f):
                    return Project.model_validate_json(f.read_text(encoding="utf-8"))
            except Exception:
                pass

        return None


def list_all() -> list[Project]:
    with lock:
        # 1. Ambil dari folder lokal (cepat ~15 ms, tanpa latency jaringan)
        projects = []
        if config.OUTPUT_DIR.exists():
            for f in config.OUTPUT_DIR.glob("*/project.json"):
                try:
                    projects.append(Project.model_validate_json(f.read_text(encoding="utf-8")))
                except Exception:
                    pass

        if projects:
            return sorted(projects, key=lambda p: p.created_at, reverse=True)

        # 2. Fallback hanya jika lokal benar-benar kosong dan D1 terhubung
        if config.has_d1():
            try:
                cloud_projects = d1.list_projects()
                if cloud_projects:
                    for p in cloud_projects:
                        d = project_dir(p.id)
                        d.mkdir(parents=True, exist_ok=True)
                        pf = d / "project.json"
                        if not pf.exists():
                            pf.write_text(p.model_dump_json(indent=2), encoding="utf-8")
                    return sorted(cloud_projects, key=lambda p: p.created_at, reverse=True)
            except Exception as e:
                logger.error(f"Failed to list from D1: {e}")

        return []


def delete(project_id: str) -> None:
    with lock:
        # 1. Hapus dari SQLite lokal
        try:
            db.delete_project_record(project_id)
        except Exception:
            pass

        # 2. Hapus folder lokal
        d = project_dir(project_id)
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
        dl_dir = config.DOWNLOADS_DIR / "stickman-flow" / project_id
        if dl_dir.exists():
            shutil.rmtree(dl_dir, ignore_errors=True)

    # 3. Async hapus dari D1 dan R2
    if config.has_d1() or config.has_r2():
        _cloud_executor.submit(_delete_from_cloud_bg, project_id)

