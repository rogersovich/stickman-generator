"""HTTP API for narration audio: voice library, per-project audio queue, and the TTS worker protocol."""

import base64
import binascii
import ipaddress
import re
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse

from . import audio, config, storage, voices
from .models import AudioCancelIn, AudioGenerateIn, AuditApproveIn, ProjectTtsIn, VoiceIn, VoiceSpeedIn, WorkerFailIn, WorkerHelloIn
from .serialize import project_out

router = APIRouter()

WORKER_PREFIX = "/api/tts-worker"
# Tailscale hands out addresses from these ranges
TRUSTED_NETS = [ipaddress.ip_network(n) for n in ("127.0.0.0/8", "::1/128", "100.64.0.0/10", "fd7a:115c:a1e0::/48")]


def _ip(request: Request):
    try:
        return ipaddress.ip_address(request.client.host) if request.client else None
    except ValueError:
        return None  # not a TCP peer (e.g. the test client)


async def trusted_network(request: Request, call_next):
    """With HOST=0.0.0.0 the app is reachable from the network: only the worker API is open to everyone."""
    ip = _ip(request)
    if ip is not None and not request.url.path.startswith(WORKER_PREFIX) and not any(ip in n for n in TRUSTED_NETS):
        return JSONResponse({"detail": "forbidden"}, status_code=403)
    return await call_next(request)


def require_worker(request: Request) -> bool:
    """Returns True when the worker runs on this machine (no token needed then)."""
    ip = _ip(request)
    if ip is not None and ip.is_loopback:
        return True
    if not config.TTS_WORKER_TOKEN:
        raise HTTPException(404)
    auth = request.headers.get("authorization", "")
    if not secrets.compare_digest(auth, f"Bearer {config.TTS_WORKER_TOKEN}"):
        raise HTTPException(401, "invalid worker token")
    return False


def _errors(fn, *args):
    try:
        return fn(*args)
    except PermissionError as e:
        raise HTTPException(409, str(e))
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


def _voice_file(voice_id: str) -> FileResponse:
    if voices.get(voice_id) is None:
        raise HTTPException(404, "voice not found")
    return FileResponse(voices.ref_path(voice_id), media_type="audio/wav")


# ---------- voice library ----------

@router.get("/api/voices")
def list_voices():
    return voices.list_voices()


@router.post("/api/voices")
def create_voice(body: VoiceIn):
    try:
        data = base64.b64decode(body.audio_base64.split(",", 1)[-1], validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(400, "audio_base64 is not valid base64")
    return _errors(voices.create, body.name, body.transcript, data, body.filename)


@router.delete("/api/voices/{voice_id}", status_code=204)
def delete_voice(voice_id: str):
    _errors(voices.delete, voice_id)


@router.get("/api/voices/{voice_id}/audio")
def voice_audio(voice_id: str):
    return _voice_file(voice_id)


@router.put("/api/voices/{voice_id}/speed")
def update_voice_speed(voice_id: str, body: VoiceSpeedIn):
    return _errors(voices.set_voice_speed, voice_id, body.speed)


@router.post("/api/voices/import-legacy")
def import_legacy_voices():
    try:
        return {"imported": voices.import_legacy(config.LEGACY_STUDIO_DB)}
    except FileNotFoundError:
        raise HTTPException(404, f"Database manhwa-recap-studio tidak ditemukan: {config.LEGACY_STUDIO_DB}")


# ---------- per-project audio ----------

@router.put("/api/projects/{project_id}/tts")
def set_project_tts(project_id: str, body: ProjectTtsIn):
    with storage.lock:
        p = _errors(audio._load, project_id)
        if body.voice_id and voices.get(body.voice_id) is None:
            raise HTTPException(400, "Suara tidak ditemukan")
        p.voice_id, p.tts_model = body.voice_id, body.tts_model
        storage.save(p)
        return project_out(p)


@router.post("/api/projects/{project_id}/audio/generate")
def generate_audio(project_id: str, body: AudioGenerateIn):
    return project_out(_errors(audio.enqueue, project_id, body.mode, body.indices))


@router.post("/api/projects/{project_id}/audio/pause")
def pause_audio(project_id: str):
    return project_out(_errors(audio.pause, project_id))


@router.post("/api/projects/{project_id}/audio/cancel")
def cancel_audio(project_id: str, body: AudioCancelIn | None = None):
    indices = body.indices if body else None
    return project_out(_errors(audio.cancel, project_id, indices))


@router.post("/api/projects/{project_id}/audio/audit")
def audit_project_audio(project_id: str):
    import subprocess, sys
    from pathlib import Path
    py_path = Path("worker-tts/.venv-ml/Scripts/python.exe")
    if not py_path.exists():
        py_path = Path("worker-tts/.venv-ml/bin/python")
    py_cmd = str(py_path.resolve()) if py_path.exists() else sys.executable
    cmd = [py_cmd, "worker-tts/audit_cli.py", project_id]
    try:
        subprocess.run(cmd, check=True, timeout=120)
    except Exception as e:
        raise HTTPException(500, f"Audit gagal: {e}")
    p = storage.load(project_id)
    if not p:
        raise HTTPException(404, "Project tidak ditemukan")
    return project_out(p)


@router.post("/api/projects/{project_id}/audio/audit-approve")
def approve_audio_audit(project_id: str, body: AuditApproveIn | None = None):
    p = storage.load(project_id)
    if not p:
        raise HTTPException(404, "Project tidak ditemukan")
    target_indices = body.indices if (body and body.indices is not None) else list(range(len(p.scenes)))
    for idx in target_indices:
        if 0 <= idx < len(p.scenes):
            p.scenes[idx].audio_audit_status = "ok"
            p.scenes[idx].audio_audit_issues = []
    storage.save(p)
    return project_out(p)


@router.get("/api/tts/status")
def tts_status():
    audio.reap()
    scenes = [s for p in storage.list_all() for s in p.scenes]
    return {
        "mode": config.TTS_WORKER_MODE,
        "workers": audio.workers_status(),
        "queued": sum(s.audio_status == "queued" for s in scenes),
        "generating": sum(s.audio_status == "generating" for s in scenes),
    }


@router.get("/files/{project_id}/audio/{name}")
def audio_file(project_id: str, name: str):
    if not re.fullmatch(r"(?:scene_\d{3}(?:_group)?|group_\d{3})\.wav", name):
        raise HTTPException(404)
    try:
        f = storage.project_dir(project_id) / "audio" / name
    except ValueError:
        raise HTTPException(404)
    if not f.is_file():
        m = re.fullmatch(r"scene_(\d{3})_group\.wav", name)
        if m:
            first_idx = int(m.group(1)) - 1
            p = storage.load(project_id)
            if p and 0 <= first_idx < len(p.scenes):
                groups = audio.get_sentence_groups(p.scenes)
                for g in groups:
                    if g and g[0] == first_idx:
                        p_dir = storage.project_dir(project_id)
                        scene_files = [(p_dir / p.scenes[si].audio_file) for si in g if p.scenes[si].audio_file]
                        if len(scene_files) == len(g) and all(sf.is_file() for sf in scene_files):
                            audio.concat_wav_files(scene_files, f)
                            return FileResponse(f, media_type="audio/wav")
        if config.has_r2():
            try:
                from . import r2
                f.parent.mkdir(parents=True, exist_ok=True)
                if r2.download_file(f"projects/{project_id}/audio/{name}", f):
                    return FileResponse(f, media_type="audio/wav")
            except Exception:
                pass
        raise HTTPException(404)
    return FileResponse(f, media_type="audio/wav")


# ---------- TTS worker protocol ----------

@router.post(f"{WORKER_PREFIX}/heartbeat", status_code=204)
def worker_heartbeat(body: WorkerHelloIn, is_local: bool = Depends(require_worker)):
    audio.heartbeat(body.name, body.models, body.device, is_local)


@router.post(f"{WORKER_PREFIX}/claim")
def worker_claim(body: WorkerHelloIn, is_local: bool = Depends(require_worker)):
    if body.device:
        audio.heartbeat(body.name, body.models, body.device, is_local)
    job = audio.claim(body.name, body.models, is_local)
    return job if job else Response(status_code=204)


@router.get(f"{WORKER_PREFIX}/voices/{{voice_id}}/audio", dependencies=[Depends(require_worker)])
def worker_voice_audio(voice_id: str):
    return _voice_file(voice_id)


@router.put(f"{WORKER_PREFIX}/jobs/{{project_id}}/{{index}}/result", status_code=204, dependencies=[Depends(require_worker)])
async def worker_result(project_id: str, index: int, key: str, request: Request, is_group: bool = False, x_worker_name: str = Header(), x_worker_audit: str | None = Header(None)):
    audit_data = None
    if x_worker_audit:
        try:
            import json, base64
            audit_json = base64.b64decode(x_worker_audit).decode('utf-8')
            audit_data = json.loads(audit_json)
        except Exception:
            pass
    if is_group:
        _errors(audio.save_group_result, project_id, index, x_worker_name, key, await request.body())
    else:
        _errors(audio.save_result, project_id, index, x_worker_name, key, await request.body(), audit_data)


@router.post(f"{WORKER_PREFIX}/jobs/{{project_id}}/{{index}}/fail", status_code=204, dependencies=[Depends(require_worker)])
def worker_fail(project_id: str, index: int, body: WorkerFailIn, x_worker_name: str = Header()):
    _errors(audio.fail, project_id, index, x_worker_name, body.error)
