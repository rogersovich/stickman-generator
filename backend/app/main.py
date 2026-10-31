import io
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from . import audio, config, d1, db, jobs, r2, routes_audio, routes_sfx, settings, storage, tts, voices
from .models import (
    CreateProjectIn,
    ImportMarkdownIn,
    JobFailIn,
    JobResultFileIn,
    JobResultIn,
    NarrationIn,
    NarrationOptionsIn,
    ParseMarkdownPreviewIn,
    Project,
    Scene,
    UpdateDraftIn,
)
from .parser import parse_markdown_prompts
from .serialize import project_out as _out
from .story import StoryError, generate_story, rewrite_narration, scene_count_for
from .styles import build_prompt, load_styles


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    if config.has_d1():
        try:
            d1.init_db()
        except Exception as e:
            import logging
            logging.getLogger("main").error(f"D1 init error: {e}")
    audio.reset_on_startup()
    for p in storage.list_all():
        try:
            db.save_project_record(p)
            if config.has_d1():
                d1.save_project(p)
        except Exception:
            pass
    yield


app = FastAPI(title="Stickman Generator", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^(http://(localhost|127\.0\.0\.1)(:\d+)?|chrome-extension://.*)$",
    allow_methods=["*"],
    allow_headers=["*"],
)
app.middleware("http")(routes_audio.trusted_network)
app.include_router(routes_audio.router)
app.include_router(routes_sfx.router)


def _get(project_id: str) -> Project:
    try:
        p = storage.load(project_id)
    except ValueError:
        p = None
    if p is None:
        raise HTTPException(404, "project not found")
    return p


@app.get("/files/{project_id}/{name}")
def get_file(project_id: str, name: str):
    try:
        f = storage.project_dir(project_id) / name
    except ValueError:
        raise HTTPException(404)
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(404)
    if f.is_file():
        return FileResponse(f)
    # If not on local disk (e.g. accessed on another device), download from R2
    if config.has_r2():
        r2_key = f"projects/{project_id}/{name}"
        if r2.download_file(r2_key, f):
            return FileResponse(f)
    raise HTTPException(404)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/config")
def get_config():
    return {
        "seconds_per_scene": settings.load().seconds_per_scene,
        "model": settings.load().default_model or config.NINEROUTER_MODEL,
        "models": config.NINEROUTER_MODEL_CHOICES,
        "fallback_models": config.NINEROUTER_FALLBACK_MODELS,
    }


@app.get("/api/settings")
def get_settings():
    return settings.load()


@app.put("/api/settings")
def put_settings(body: settings.AppSettings):
    if body.default_model not in config.NINEROUTER_MODEL_CHOICES:
        raise HTTPException(400, f"unknown model: {body.default_model}")
    if body.rewrite_model not in config.NINEROUTER_MODEL_CHOICES:
        raise HTTPException(400, f"unknown rewrite model: {body.rewrite_model}")
    if body.default_style_id not in load_styles():
        raise HTTPException(400, f"unknown style: {body.default_style_id}")
    return settings.save(body)


@app.get("/api/styles")
def get_styles():
    return [{"id": s["id"], "name": s["name"]} for s in load_styles().values()]


# ---------- projects ----------

@app.get("/api/projects")
def list_projects():
    return [
        {
            "id": p.id,
            "title": p.title,
            "format": p.format,
            "status": p.status,
            "scene_count": len(p.scenes),
            "done_count": sum(s.image_status == "done" for s in p.scenes),
            "low_res_count": sum(jobs.needs_hd(p.id, s) for s in p.scenes),
            "created_at": p.created_at,
        }
        for p in storage.list_all()
    ]


@app.post("/api/projects")
def create_project(body: CreateProjectIn):
    if body.style_id not in load_styles():
        raise HTTPException(400, f"unknown style: {body.style_id}")
    if body.model and body.model not in config.NINEROUTER_MODEL_CHOICES:
        raise HTTPException(400, f"unknown model: {body.model}")
    count = body.scene_count or scene_count_for(body.duration_sec)
    try:
        draft = generate_story(body.topic, count, body.language, body.style_id, body.model or settings.load().default_model)
    except StoryError as e:
        raise HTTPException(502, str(e))
    p = Project(
        id=storage.new_project_id(body.topic),
        title=draft.title or body.topic,
        topic=body.topic,
        core_answer=draft.core_answer,
        story_model=draft.model,
        format=body.format,
        duration_sec=body.duration_sec,
        style_id=body.style_id,
        language=body.language,
        scenes=draft.scenes,
    )
    storage.save(p)
    return _out(p)


@app.post("/api/projects/parse-markdown-preview")
def preview_markdown(body: ParseMarkdownPreviewIn):
    if not body.markdown.strip():
        raise HTTPException(400, "markdown content cannot be empty")
    return parse_markdown_prompts(body.markdown)


@app.post("/api/projects/import-markdown")
def import_markdown(body: ImportMarkdownIn):
    if not body.markdown.strip():
        raise HTTPException(400, "markdown content cannot be empty")

    parsed = parse_markdown_prompts(body.markdown)
    if not parsed["scenes"]:
        raise HTTPException(400, "no scenes found in markdown (make sure sections start with '## Scene')")

    title = body.title.strip() if (body.title and body.title.strip()) else parsed["title"]
    fmt = body.format or parsed["format"]

    scenes: list[Scene] = []
    total_words = 0
    for s_data in parsed["scenes"]:
        narr = s_data["narration"]
        total_words += len(narr.split())
        scenes.append(
            Scene(
                narration=narr,
                prompt=s_data["prompt"],
                tag=s_data["tag"],
                is_merged=s_data["is_merged"],
                merged_with=s_data["merged_with"],
                scene_description=s_data["tag"] or narr,
                image_status="pending",
            )
        )

    duration_sec = max(60, int(total_words / 2.5)) if total_words else 60

    p = Project(
        id=storage.new_project_id(title),
        title=title,
        topic=title,
        core_answer=f"Diimpor dari file markdown prompt ({len(scenes)} adegan)",
        story_model="Markdown Import",
        format=fmt,
        duration_sec=duration_sec,
        style_id=body.style_id,
        language="Indonesia",
        status="draft",
        scenes=scenes,
    )

    if body.auto_confirm:
        p.status = "generating"

    storage.save(p)
    return _out(p)


@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    return _out(_get(project_id))


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str):
    """Delete the project folder (project.json + all images)."""
    with storage.lock:
        p = _get(project_id)
        # a worker that died mid-job never releases its scenes: don't let them block forever
        jobs.expire_stale(p)
        if any(s.image_status == "generating" for s in p.scenes):
            raise HTTPException(409, "a scene is being generated right now: pause the project or turn the worker OFF first")
        storage.delete(project_id)
    return {"ok": True}


@app.put("/api/projects/{project_id}")
def update_draft(project_id: str, body: UpdateDraftIn):
    with storage.lock:
        p = _get(project_id)
        if p.status != "draft":
            raise HTTPException(409, "only drafts can be edited")
        if not body.scenes:
            raise HTTPException(400, "at least one scene is required")
        p.title = body.title
        p.core_answer = body.core_answer
        p.scenes = [Scene(**s.model_dump()) for s in body.scenes]
        storage.save(p)
        return _out(p)


@app.get("/api/projects/{project_id}/prompts")
def get_prompts(project_id: str):
    p = _get(project_id)
    return [build_prompt(p, s) for s in p.scenes]


@app.post("/api/projects/{project_id}/scenes/{index}/narration-options")
def narration_options(project_id: str, index: int, body: NarrationOptionsIn):
    """Ask the LLM for 3 alternative narrations of one scene (nothing is saved)."""
    p = _get(project_id)
    if not 0 <= index < len(p.scenes):
        raise HTTPException(404, "scene not found")
    scene = p.scenes[index]
    try:
        options, model = rewrite_narration(
            title=p.title,
            topic=p.topic,
            core_answer=p.core_answer,
            language=p.language,
            narrations=[s.narration for s in p.scenes],
            index=index,
            scene_description=scene.scene_description,
            title_text=scene.title_text,
            mode=body.mode,
            instruction=body.instruction,
            model=settings.load().rewrite_model,
        )
    except StoryError as e:
        raise HTTPException(502, str(e))
    return {"options": options, "model": model}


@app.put("/api/projects/{project_id}/scenes/{index}/narration")
def set_narration(project_id: str, index: int, body: NarrationIn):
    """Replace one scene's narration. Allowed in any status: the image doesn't depend on it."""
    with storage.lock:
        p = _get(project_id)
        if not 0 <= index < len(p.scenes):
            raise HTTPException(404, "scene not found")
        p.scenes[index].narration = body.narration.strip()
        storage.save(p)
        return _out(p)


@app.post("/api/projects/{project_id}/confirm")
def confirm(project_id: str):
    with storage.lock:
        p = _get(project_id)
        if p.status != "draft":
            raise HTTPException(409, "project already confirmed")
        p.status = "generating"
        for s in p.scenes:
            s.image_status, s.image_file, s.error = "pending", None, None
        storage.save(p)
        return _out(p)


@app.post("/api/projects/{project_id}/pause")
def pause(project_id: str):
    with storage.lock:
        p = _get(project_id)
        if p.status == "generating":
            p.status = "paused"
            storage.save(p)
        return _out(p)


@app.post("/api/projects/{project_id}/resume")
def resume(project_id: str):
    with storage.lock:
        p = _get(project_id)
        if p.status in ("paused", "done") and any(s.image_status != "done" for s in p.scenes):
            p.status = "generating"
            storage.save(p)
        return _out(p)


@app.post("/api/projects/{project_id}/clear-images")
def clear_project_images(project_id: str):
    with storage.lock:
        p = _get(project_id)
        # a worker that died mid-job never releases its scenes: don't let them block forever
        jobs.expire_stale(p)
        if any(s.image_status == "generating" for s in p.scenes):
            raise HTTPException(409, "Ada scene yang sedang di-generate. Jeda dulu worker sebelum membersihkan gambar.")
        p = jobs.clear_images(project_id)
        return _out(p)


@app.post("/api/projects/{project_id}/test-run")
def test_run(project_id: str, limit: int = 2):
    with storage.lock:
        p = jobs.set_test_run(project_id, limit=limit)
        return _out(p)


@app.post("/api/projects/{project_id}/swap-scenes")
def swap_scenes(project_id: str, a: int, b: int):
    """Swap image assignment between two scenes."""
    import time
    with storage.lock:
        p = _get(project_id)
        if not (0 <= a < len(p.scenes) and 0 <= b < len(p.scenes)):
            raise HTTPException(400, "index scene tidak valid")
        s_a = p.scenes[a]
        s_b = p.scenes[b]
        d = storage.project_dir(project_id)
        file_a = s_a.image_file
        file_b = s_b.image_file
        # Swap files on disk if present
        if file_a and file_b and (d / file_a).exists() and (d / file_b).exists():
            tmp = d / f"tmp_swap_{time.time()}.bin"
            (d / file_a).rename(tmp)
            (d / file_b).rename(d / file_a)
            tmp.rename(d / file_b)
        # Swap scene metadata
        s_a.image_status, s_b.image_status = s_b.image_status, s_a.image_status
        s_a.image_file, s_b.image_file = s_b.image_file, s_a.image_file
        s_a.flow_src, s_b.flow_src = s_b.flow_src, s_a.flow_src
        s_a.image_hd, s_b.image_hd = s_b.image_hd, s_a.image_hd
        s_a.error, s_b.error = s_b.error, s_a.error
        storage.save(p)
        return _out(p)


@app.post("/api/projects/{project_id}/scenes/{index}/retry")
def retry_scene(project_id: str, index: int):
    with storage.lock:
        p = _get(project_id)
        if not 0 <= index < len(p.scenes):
            raise HTTPException(404, "scene not found")
        s = p.scenes[index]
        s.image_status, s.error, s.job_kind = "pending", None, "generate"
        if p.status == "done":
            p.status = "generating"
        storage.save(p)
        return _out(p)


@app.post("/api/projects/{project_id}/redownload")
def redownload_all(project_id: str):
    """Re-fetch full-res files for every scene that only has a thumbnail."""
    try:
        return _out(jobs.request_redownload(project_id))
    except (LookupError, ValueError) as e:
        raise HTTPException(404, str(e))


@app.post("/api/projects/{project_id}/scenes/{index}/redownload")
def redownload_scene(project_id: str, index: int):
    try:
        return _out(jobs.request_redownload(project_id, [index]))
    except (LookupError, ValueError) as e:
        raise HTTPException(404, str(e))


@app.get("/api/projects/{project_id}/download")
def download(project_id: str):
    p = _get(project_id)
    d = storage.project_dir(project_id)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(d / "project.json", "project.json")
        script = "\n\n".join(f"[{i + 1}] {s.narration}" for i, s in enumerate(p.scenes))
        z.writestr("narration.txt", f"{p.title}\n\n{script}\n")

        # Write each scene image sequentially so merged scenes also have a corresponding image file in the zip
        for i, s in enumerate(p.scenes):
            if s.image_file and (d / s.image_file).exists():
                src_path = d / s.image_file
                out_name = f"scene_{i + 1:03d}{src_path.suffix}"
                z.write(src_path, out_name)
            if s.audio_file and (d / s.audio_file).exists():
                src_audio = d / s.audio_file
                out_name = f"scene_{i + 1:03d}.wav"
                z.write(src_audio, out_name)
                if s.audio_file != out_name:
                    z.write(src_audio, s.audio_file)

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{project_id}.zip"'},
    )


# ---------- Voices & TTS ----------


@app.post("/api/projects/{project_id}/generate-audio")
def generate_project_audio(project_id: str, voice_id: str = "suara-1", force: bool = False):
    p = _get(project_id)
    if not p.scenes:
        raise HTTPException(400, "project has no scenes")
    success = tts.start_voice_generation(project_id, voice_id=voice_id, force=force)
    if not success:
        raise HTTPException(409, "audio generation already in progress or failed to start")
    return {"ok": True, "project_id": project_id, "voice_status": "generating"}


@app.post("/api/projects/{project_id}/scenes/{index}/generate-audio")
def generate_scene_audio(project_id: str, index: int, voice_id: str = "suara-1"):
    p = _get(project_id)
    if not (0 <= index < len(p.scenes)):
        raise HTTPException(404, "scene not found")
    success = tts.start_voice_generation(project_id, voice_id=voice_id, scene_index=index, force=True)
    if not success:
        raise HTTPException(409, "audio generation already in progress or failed to start")
    return {"ok": True, "project_id": project_id, "scene_index": index}


@app.post("/api/projects/{project_id}/stop-audio")
def stop_project_audio(project_id: str):
    p = _get(project_id)
    tts.stop_voice_generation(project_id)
    return {"ok": True, "voice_status": "idle"}


# ---------- Cloudflare D1 & R2 Storage Status & Backup ----------

@app.get("/api/storage/status")
def get_storage_status():
    projects = storage.list_all()
    total_projects = len(projects)
    r2_stats = r2.get_storage_stats() if config.has_r2() else {}
    threshold = config.BACKUP_PROJECT_THRESHOLD
    needs_backup = total_projects >= threshold

    dest = config.GDRIVE_BACKUP_DESTINATION or f"{config.GDRIVE_REMOTE_NAME}:{config.GDRIVE_FOLDER_NAME}"
    cfg_arg = f' --config "{config.RCLONE_CONFIG_PATH}"'
    rclone_cmd = (
        f"rclone copy :s3,provider=Cloudflare,endpoint='{config.R2_ENDPOINT_URL}',"
        f"access_key_id='{config.R2_ACCESS_KEY_ID}',"
        f"secret_access_key='{config.R2_SECRET_ACCESS_KEY}':{config.R2_BUCKET_NAME} "
        f"{dest}{cfg_arg} --progress"
    )

    rclone_conf_candidates = [
        Path(config.RCLONE_CONFIG_PATH),
        Path("..") / config.RCLONE_CONFIG_PATH,
        Path(__file__).resolve().parent.parent.parent / config.RCLONE_CONFIG_PATH,
    ]
    gdrive_configured = False
    for p in rclone_conf_candidates:
        if p.exists():
            text = p.read_text(encoding="utf-8", errors="ignore")
            if f"[{config.GDRIVE_REMOTE_NAME}]" in text and "token" in text:
                gdrive_configured = True
                break

    return {
        "d1_connected": config.has_d1(),
        "r2_connected": config.has_r2(),
        "total_projects": total_projects,
        "backup_threshold": threshold,
        "needs_backup": needs_backup,
        "gdrive_email": config.GDRIVE_EMAIL,
        "gdrive_remote_name": config.GDRIVE_REMOTE_NAME,
        "gdrive_destination": dest,
        "gdrive_configured": gdrive_configured,
        "rclone_config_path": config.RCLONE_CONFIG_PATH,
        "r2_stats": r2_stats,
        "rclone_backup_command": rclone_cmd,
    }


# ---------- jobs (used by the browser extension) ----------

@app.get("/api/jobs/next")
def get_next_job():
    job = jobs.next_job()
    if job is None:
        return Response(status_code=204)
    return job


@app.post("/api/jobs/{project_id}/{index}/result")
def post_result(project_id: str, index: int, body: JobResultIn):
    try:
        jobs.save_result(project_id, index, body.image_base64, body.mime, body.note, flow_src=body.flow_src)
    except LookupError as e:
        raise HTTPException(404, str(e))
    return {"ok": True}


@app.post("/api/jobs/{project_id}/{index}/result-file")
def post_result_file(project_id: str, index: int, body: JobResultFileIn):
    try:
        jobs.save_result_file(project_id, index, body.path, body.note)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except (PermissionError, FileNotFoundError, ValueError) as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.post("/api/jobs/{project_id}/{index}/fail")
def post_fail(project_id: str, index: int, body: JobFailIn):
    try:
        jobs.mark_failed(project_id, index, body.error)
    except LookupError as e:
        raise HTTPException(404, str(e))
    return {"ok": True}


@app.post("/api/jobs/{project_id}/{index}/release")
def post_release(project_id: str, index: int):
    try:
        jobs.release(project_id, index)
    except LookupError as e:
        raise HTTPException(404, str(e))
    return {"ok": True}


class CapCutExportIn(BaseModel):
    drafts_dir: str | None = None
    project_name: str | None = None
    ken_burns: bool = True
    enable_zoom: bool = True
    enable_pan: bool = True
    zoom_ratio: float = 1.15
    enable_transitions: bool = True
    transition_duration: float = 0.5
    allowed_transitions: list[str] | None = None
    include_sfx: bool = True


@app.get("/api/capcut/transitions")
def get_capcut_transitions():
    from .capcut_transitions import list_transitions
    return {"transitions": list_transitions()}


class ExportOptsIn(BaseModel):
    ken_burns: bool = True
    enable_zoom: bool = True
    enable_pan: bool = True
    zoom_ratio: float = 1.15
    enable_transitions: bool = True
    transition_duration: float = 0.5
    allowed_transitions: list[str] | None = None
    include_sfx: bool = True


@app.put("/api/projects/{project_id}/export-opts")
def save_export_opts(project_id: str, body: ExportOptsIn):
    p = _get(project_id)
    p.export_opts = body.model_dump()
    storage.save(p)
    return _out(p)


@app.post("/api/projects/{project_id}/export-capcut")
def export_capcut(project_id: str, body: CapCutExportIn = CapCutExportIn()):
    try:
        from .capcut_service import export_project_to_capcut
        return export_project_to_capcut(
            project_id=project_id,
            drafts_dir=body.drafts_dir,
            project_name=body.project_name,
            ken_burns=body.ken_burns,
            enable_zoom=body.enable_zoom,
            enable_pan=body.enable_pan,
            zoom_ratio=body.zoom_ratio,
            enable_transitions=body.enable_transitions,
            transition_duration=body.transition_duration,
            allowed_transitions=body.allowed_transitions,
            include_sfx=body.include_sfx,
        )
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Gagal ekspor CapCut: {e}")

