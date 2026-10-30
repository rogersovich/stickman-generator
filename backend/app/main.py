import io
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from . import config, db, jobs, settings, storage
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
from .story import StoryError, generate_story, rewrite_narration, scene_count_for
from .styles import build_prompt, load_styles


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    for p in storage.list_all():
        try:
            db.save_project_record(p)
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


def _get(project_id: str) -> Project:
    try:
        p = storage.load(project_id)
    except ValueError:
        p = None
    if p is None:
        raise HTTPException(404, "project not found")
    return p


def _out(p: Project) -> dict:
    """Project as JSON, plus whether each scene is still only a low-res thumbnail."""
    data = p.model_dump()
    for scene, out in zip(p.scenes, data["scenes"]):
        out["needs_hd"] = jobs.needs_hd(p.id, scene)
    return data


@app.get("/files/{project_id}/{name}")
def get_file(project_id: str, name: str):
    try:
        f = storage.project_dir(project_id) / name
    except ValueError:
        raise HTTPException(404)
    if "/" in name or ".." in name or not f.is_file():
        raise HTTPException(404)
    return FileResponse(f)


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
        if any(s.image_status == "generating" for s in p.scenes):
            raise HTTPException(409, "Ada scene yang sedang di-generate. Jeda dulu worker sebelum membersihkan gambar.")
        p = jobs.clear_images(project_id)
        return _out(p)


@app.post("/api/projects/{project_id}/test-run")
def test_run(project_id: str, limit: int = 2):
    with storage.lock:
        p = jobs.set_test_run(project_id, limit=limit)
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

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{project_id}.zip"'},
    )


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
