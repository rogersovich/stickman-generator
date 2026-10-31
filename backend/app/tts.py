"""TTS Process Manager for Stickman Generator."""

import subprocess
import sys
from pathlib import Path
from typing import Optional

from . import config, storage
from .models import Project

PYTHON_ML = Path(r"D:\Coding\Python\manhwa-recap-studio\.venv-ml\Scripts\python.exe")
RUNNER_SCRIPT = Path(__file__).resolve().parent / "tts_runner.py"

# Active subprocesses keyed by project_id
_active_jobs: dict[str, subprocess.Popen] = {}

def get_python_exe() -> str:
    if PYTHON_ML.exists():
        return str(PYTHON_ML)
    return sys.executable

def start_voice_generation(
    project_id: str,
    voice_id: str = "suara-1",
    scene_index: Optional[int] = None,
    force: bool = False,
) -> bool:
    """Start TTS generation for a project or a single scene."""
    p_dir = storage.project_dir(project_id)
    if not p_dir.exists():
        return False

    # Check if a process is already running for this project
    existing = _active_jobs.get(project_id)
    if existing and existing.poll() is None:
        return False  # Already running

    cmd = [
        get_python_exe(),
        str(RUNNER_SCRIPT),
        "--project_dir",
        str(p_dir),
        "--voice_id",
        voice_id,
    ]
    if scene_index is not None:
        cmd.extend(["--scene_index", str(scene_index)])
    if force:
        cmd.append("--force")

    # Mark project as generating
    project = storage.load(project_id)
    if project:
        project.voice_status = "generating"
        project.voice_error = None
        storage.save(project)

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    _active_jobs[project_id] = proc
    return True

def stop_voice_generation(project_id: str) -> bool:
    """Stop running TTS generation for a project."""
    proc = _active_jobs.get(project_id)
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
        _active_jobs.pop(project_id, None)

        project = storage.load(project_id)
        if project:
            project.voice_status = "idle"
            for s in project.scenes:
                if s.audio_status == "generating":
                    s.audio_status = "idle"
            storage.save(project)
        return True
    return False

def is_generating(project_id: str) -> bool:
    proc = _active_jobs.get(project_id)
    if proc:
        if proc.poll() is None:
            return True
        _active_jobs.pop(project_id, None)
    return False

