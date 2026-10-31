"""HTTP API for the sound-effect library and per-scene SFX of the CapCut export."""

import base64
import binascii

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from . import sfx, storage
from .models import SceneSfxIn, SfxIn, SfxUpdateIn
from .serialize import project_out

router = APIRouter()


def _errors(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/api/sfx")
def list_sfx():
    return sfx.list_catalog()


@router.post("/api/sfx")
def upload_sfx(body: SfxIn):
    try:
        data = base64.b64decode(body.audio_base64.split(",", 1)[-1], validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(400, "audio_base64 is not valid base64")
    return _errors(sfx.add_custom, data, body.filename, body.volume)


@router.patch("/api/sfx/{sfx_id}")
def update_sfx(sfx_id: str, body: SfxUpdateIn):
    return _errors(sfx.update, sfx_id, label=body.label, volume=body.volume)


@router.delete("/api/sfx/{sfx_id}", status_code=204)
def delete_sfx(sfx_id: str):
    _errors(sfx.delete_custom, sfx_id)


@router.get("/api/sfx/{sfx_id}/audio")
def sfx_audio(sfx_id: str):
    if sfx.get(sfx_id) is None:
        raise HTTPException(404, "SFX tidak ditemukan")
    return FileResponse(sfx.path(sfx_id), media_type="audio/wav")


@router.put("/api/projects/{project_id}/scenes/{index}/sfx")
def set_scene_sfx(project_id: str, index: int, body: SceneSfxIn):
    if body.sfx_id and sfx.get(body.sfx_id) is None:
        raise HTTPException(400, "SFX tidak ditemukan")
    with storage.lock:
        p = _errors(storage.load, project_id)
        if p is None:
            raise HTTPException(404, "project not found")
        if not 0 <= index < len(p.scenes):
            raise HTTPException(404, "scene not found")
        p.scenes[index].sfx_id = body.sfx_id or None
        p.scenes[index].sfx_pos = body.sfx_pos
        storage.save(p)
        return project_out(p)
