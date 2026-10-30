import sqlite3
import threading
from pathlib import Path
from typing import Any

from . import config

DB_PATH = config.BACKEND_DIR / "data" / "stickman.db"
_lock = threading.RLock()


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _lock:
        conn = get_conn()
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    topic TEXT,
                    format TEXT,
                    status TEXT,
                    style_id TEXT,
                    scene_count INTEGER DEFAULT 0,
                    done_count INTEGER DEFAULT 0,
                    created_at TEXT,
                    updated_at TEXT,
                    data_json TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scenes (
                    project_id TEXT NOT NULL,
                    scene_index INTEGER NOT NULL,
                    narration TEXT,
                    prompt TEXT,
                    tag TEXT,
                    image_status TEXT,
                    image_file TEXT,
                    flow_src TEXT,
                    image_blob BLOB,
                    error TEXT,
                    started_at TEXT,
                    image_hd INTEGER,
                    job_kind TEXT,
                    updated_at TEXT,
                    PRIMARY KEY (project_id, scene_index)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    scene_index INTEGER NOT NULL,
                    flow_src TEXT,
                    image_blob BLOB NOT NULL,
                    mime TEXT,
                    note TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_scenes_proj ON scenes(project_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_proj ON snapshots(project_id, scene_index)")
        conn.close()


def save_project_record(project: Any) -> None:
    """Save or update project metadata and scenes in SQLite."""
    with _lock:
        conn = get_conn()
        with conn:
            done_count = sum(1 for s in project.scenes if getattr(s, "image_status", None) == "done")
            conn.execute("""
                INSERT INTO projects (id, title, topic, format, status, style_id, scene_count, done_count, created_at, updated_at, data_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    topic=excluded.topic,
                    format=excluded.format,
                    status=excluded.status,
                    style_id=excluded.style_id,
                    scene_count=excluded.scene_count,
                    done_count=excluded.done_count,
                    updated_at=excluded.updated_at,
                    data_json=excluded.data_json
            """, (
                project.id,
                project.title,
                project.topic,
                project.format,
                project.status,
                project.style_id,
                len(project.scenes),
                done_count,
                project.created_at,
                project.updated_at,
                project.model_dump_json(),
            ))
            for i, s in enumerate(project.scenes):
                conn.execute("""
                    INSERT INTO scenes (project_id, scene_index, narration, prompt, tag, image_status, image_file, flow_src, error, started_at, image_hd, job_kind, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(project_id, scene_index) DO UPDATE SET
                        narration=excluded.narration,
                        prompt=excluded.prompt,
                        tag=excluded.tag,
                        image_status=excluded.image_status,
                        image_file=excluded.image_file,
                        flow_src=excluded.flow_src,
                        error=excluded.error,
                        started_at=excluded.started_at,
                        image_hd=excluded.image_hd,
                        job_kind=excluded.job_kind,
                        updated_at=excluded.updated_at
                """, (
                    project.id,
                    i,
                    getattr(s, "narration", ""),
                    getattr(s, "prompt", ""),
                    getattr(s, "tag", ""),
                    getattr(s, "image_status", "pending"),
                    getattr(s, "image_file", None),
                    getattr(s, "flow_src", None),
                    getattr(s, "error", None),
                    getattr(s, "started_at", None),
                    1 if getattr(s, "image_hd", None) is True else (0 if getattr(s, "image_hd", None) is False else None),
                    getattr(s, "job_kind", "generate"),
                    project.updated_at,
                ))
        conn.close()


def save_snapshot_record(project_id: str, scene_index: int, image_bytes: bytes, mime: str, flow_src: str | None = None, note: str | None = None) -> None:
    """Save raw image snapshot bytes directly into SQLite snapshots and scenes tables."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    with _lock:
        conn = get_conn()
        with conn:
            conn.execute("""
                INSERT INTO snapshots (project_id, scene_index, flow_src, image_blob, mime, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (project_id, scene_index, flow_src, image_bytes, mime, note, now))
            conn.execute("""
                UPDATE scenes SET image_blob = ?, flow_src = coalesce(?, flow_src), updated_at = ?
                WHERE project_id = ? AND scene_index = ?
            """, (image_bytes, flow_src, now, project_id, scene_index))
        conn.close()


def clear_project_snapshots(project_id: str) -> None:
    """Clear image blobs and snapshots for a project in SQLite."""
    with _lock:
        conn = get_conn()
        with conn:
            conn.execute("DELETE FROM snapshots WHERE project_id = ?", (project_id,))
            conn.execute("UPDATE scenes SET image_blob = NULL, image_file = NULL, flow_src = NULL, image_status = 'pending', error = NULL WHERE project_id = ?", (project_id,))
        conn.close()


def delete_project_record(project_id: str) -> None:
    """Remove project and all its scenes and snapshots from SQLite."""
    with _lock:
        conn = get_conn()
        with conn:
            conn.execute("DELETE FROM snapshots WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM scenes WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.close()
