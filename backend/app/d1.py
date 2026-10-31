"""Cloudflare D1 Client for Stickman Generator."""

import json
import logging
import urllib.request
import urllib.error
from typing import Any, Optional

from . import config
from .models import Project

logger = logging.getLogger("d1")

def _query_d1(sql: str, params: Optional[list] = None) -> list[dict[str, Any]]:
    if not config.has_d1():
        raise RuntimeError("Cloudflare D1 credentials not configured")

    url = (
        f"https://api.cloudflare.com/client/v4/accounts/"
        f"{config.CLOUDFLARE_ACCOUNT_ID}/d1/database/"
        f"{config.CLOUDFLARE_D1_DATABASE_ID}/query"
    )
    headers = {
        "Authorization": f"Bearer {config.CLOUDFLARE_API_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {"sql": sql}
    if params:
        payload["params"] = params

    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if not data.get("success"):
                errors = data.get("errors", [])
                raise RuntimeError(f"D1 error: {errors}")
            result_list = data.get("result", [])
            if result_list and isinstance(result_list, list):
                return result_list[0].get("results", [])
            return []
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8")
        logger.error(f"D1 HTTP Error {e.code}: {err_msg}")
        raise RuntimeError(f"D1 HTTP {e.code}: {err_msg}")


def init_db() -> None:
    """Initialize Cloudflare D1 tables."""
    if not config.has_d1():
        return

    _query_d1("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            topic TEXT,
            format TEXT,
            status TEXT,
            voice_id TEXT,
            voice_status TEXT,
            voice_error TEXT,
            style_id TEXT,
            duration_sec INTEGER,
            created_at TEXT,
            updated_at TEXT,
            data_json TEXT NOT NULL
        )
    """)

    _query_d1("""
        CREATE TABLE IF NOT EXISTS scenes (
            project_id TEXT NOT NULL,
            scene_index INTEGER NOT NULL,
            narration TEXT,
            prompt TEXT,
            tag TEXT,
            title_text TEXT,
            scene_description TEXT,
            image_status TEXT,
            image_file TEXT,
            flow_src TEXT,
            audio_status TEXT,
            audio_file TEXT,
            error TEXT,
            audio_error TEXT,
            started_at TEXT,
            image_hd INTEGER,
            job_kind TEXT,
            is_merged INTEGER,
            merged_with INTEGER,
            updated_at TEXT,
            PRIMARY KEY (project_id, scene_index)
        )
    """)


def save_project(project: Project) -> None:
    """Save project & scene records to Cloudflare D1."""
    if not config.has_d1():
        return

    data_json = project.model_dump_json()

    _query_d1("""
        INSERT INTO projects (
            id, title, topic, format, status, voice_id, voice_status, voice_error,
            style_id, duration_sec, created_at, updated_at, data_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            title = excluded.title,
            topic = excluded.topic,
            format = excluded.format,
            status = excluded.status,
            voice_id = excluded.voice_id,
            voice_status = excluded.voice_status,
            voice_error = excluded.voice_error,
            style_id = excluded.style_id,
            duration_sec = excluded.duration_sec,
            updated_at = excluded.updated_at,
            data_json = excluded.data_json
    """, [
        project.id,
        project.title,
        project.topic,
        project.format,
        project.status,
        project.voice_id,
        project.voice_status,
        project.voice_error,
        project.style_id,
        project.duration_sec,
        project.created_at,
        project.updated_at,
        data_json,
    ])


def load_project(project_id: str) -> Optional[Project]:
    if not config.has_d1():
        return None
    rows = _query_d1("SELECT data_json FROM projects WHERE id = ? LIMIT 1", [project_id])
    if not rows:
        return None
    try:
        return Project.model_validate_json(rows[0]["data_json"])
    except Exception as e:
        logger.error(f"Failed to validate project from D1: {e}")
        return None


def list_projects() -> list[Project]:
    if not config.has_d1():
        return []
    rows = _query_d1("SELECT data_json FROM projects ORDER BY created_at DESC")
    projects = []
    for r in rows:
        try:
            projects.append(Project.model_validate_json(r["data_json"]))
        except Exception:
            pass
    return projects


def delete_project(project_id: str) -> None:
    if not config.has_d1():
        return
    _query_d1("DELETE FROM scenes WHERE project_id = ?", [project_id])
    _query_d1("DELETE FROM projects WHERE id = ?", [project_id])


def count_projects() -> int:
    if not config.has_d1():
        return 0
    rows = _query_d1("SELECT COUNT(*) as count FROM projects")
    return int(rows[0].get("count", 0)) if rows else 0

