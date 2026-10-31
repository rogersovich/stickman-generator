import re
import shutil
import threading
import time
from pathlib import Path

from . import config, d1, db, r2
from .models import Project, now_iso

lock = threading.RLock()


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:40] or "project"


def new_project_id(topic: str) -> str:
    return f"{slugify(topic)}-{time.strftime('%Y%m%d-%H%M%S')}"


def project_dir(project_id: str) -> Path:
    if not re.fullmatch(r"[a-z0-9-]+", project_id):
        raise ValueError("invalid project id")
    return config.OUTPUT_DIR / project_id


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

        # 2. Sync to Cloudflare D1
        if config.has_d1():
            try:
                d1.save_project(project)
            except Exception as e:
                import logging
                logging.getLogger("storage").error(f"Failed to sync project to D1: {e}")

        # 3. Sync project metadata to Cloudflare R2
        if config.has_r2():
            try:
                r2.upload_file(project_file, f"projects/{project.id}/project.json", "application/json")
            except Exception:
                pass


def load(project_id: str) -> Project | None:
    with lock:
        d = project_dir(project_id)
        f = d / "project.json"

        local_proj = None
        if f.exists():
            try:
                local_proj = Project.model_validate_json(f.read_text(encoding="utf-8"))
            except Exception:
                pass

        # 1. Jika terhubung Cloudflare D1, sinkronkan dengan versi cloud terbaru
        if config.has_d1():
            try:
                remote_proj = d1.load_project(project_id)
                if remote_proj:
                    if local_proj is None or (remote_proj.updated_at or "") > (local_proj.updated_at or ""):
                        d.mkdir(parents=True, exist_ok=True)
                        f.write_text(remote_proj.model_dump_json(indent=2), encoding="utf-8")
                        return remote_proj
                    return local_proj
            except Exception:
                pass

        if local_proj:
            return local_proj

        # 2. Fallback: coba unduh dari R2
        if config.has_r2():
            try:
                if r2.download_file(f"projects/{project_id}/project.json", f):
                    return Project.model_validate_json(f.read_text(encoding="utf-8"))
            except Exception:
                pass

        return None


def list_all() -> list[Project]:
    with lock:
        # 1. Jika terhubung D1, gunakan D1 sebagai single source of truth lintas device
        if config.has_d1():
            try:
                projects = d1.list_projects()
                if projects:
                    # Sync local directory cache
                    for p in projects:
                        d = project_dir(p.id)
                        d.mkdir(parents=True, exist_ok=True)
                        pf = d / "project.json"
                        if not pf.exists():
                            pf.write_text(p.model_dump_json(indent=2), encoding="utf-8")
                        else:
                            try:
                                local_p = Project.model_validate_json(pf.read_text(encoding="utf-8"))
                                if (p.updated_at or "") > (local_p.updated_at or ""):
                                    pf.write_text(p.model_dump_json(indent=2), encoding="utf-8")
                            except Exception:
                                pass
                    return projects
            except Exception as e:
                import logging
                logging.getLogger("storage").error(f"Failed to list from D1: {e}")

        # 2. Fallback ke folder lokal jika D1 belum dikonfigurasi / offline
        if not config.OUTPUT_DIR.exists():
            return []
        projects = []
        for f in config.OUTPUT_DIR.glob("*/project.json"):
            try:
                projects.append(Project.model_validate_json(f.read_text(encoding="utf-8")))
            except Exception:
                pass
        return sorted(projects, key=lambda p: p.created_at, reverse=True)


def delete(project_id: str) -> None:
    with lock:
        # 1. Hapus dari D1
        if config.has_d1():
            try:
                d1.delete_project(project_id)
            except Exception:
                pass

        # 2. Hapus aset media di Cloudflare R2
        if config.has_r2():
            try:
                r2.delete_prefix(f"projects/{project_id}/")
            except Exception:
                pass

        # 3. Hapus dari SQLite lokal
        try:
            db.delete_project_record(project_id)
        except Exception:
            pass

        # 4. Hapus folder lokal
        d = project_dir(project_id)
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
        dl_dir = config.DOWNLOADS_DIR / "stickman-flow" / project_id
        if dl_dir.exists():
            shutil.rmtree(dl_dir, ignore_errors=True)
