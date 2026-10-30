import re
import shutil
import threading
import time
from pathlib import Path

from . import config, db
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
        tmp = d / "project.json.tmp"
        tmp.write_text(project.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(d / "project.json")
        try:
            db.save_project_record(project)
        except Exception:
            pass


def load(project_id: str) -> Project | None:
    with lock:
        f = project_dir(project_id) / "project.json"
        if not f.exists():
            return None
        return Project.model_validate_json(f.read_text(encoding="utf-8"))


def list_all() -> list[Project]:
    with lock:
        if not config.OUTPUT_DIR.exists():
            return []
        projects = [
            Project.model_validate_json(f.read_text(encoding="utf-8"))
            for f in config.OUTPUT_DIR.glob("*/project.json")
        ]
    return sorted(projects, key=lambda p: p.created_at, reverse=True)


def delete(project_id: str) -> None:
    with lock:
        d = project_dir(project_id)
        if not (d / "project.json").exists():
            raise LookupError("project not found")
        shutil.rmtree(d)
        dl_dir = config.DOWNLOADS_DIR / "stickman-flow" / project_id
        if dl_dir.exists():
            shutil.rmtree(dl_dir, ignore_errors=True)
        try:
            db.delete_project_record(project_id)
        except Exception:
            pass
