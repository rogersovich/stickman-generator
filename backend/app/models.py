from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

Format = Literal["9:16", "16:9"]
ProjectStatus = Literal["draft", "generating", "paused", "done"]
ImageStatus = Literal["pending", "generating", "done", "failed"]
JobKind = Literal["generate", "redownload"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Scene(BaseModel):
    narration: str = ""
    scene_description: str = ""
    title_text: str = ""
    prompt: str = ""  # Full prompt if pre-computed or imported from markdown
    tag: str = ""  # e.g. "WIDE SHOT 10%", "DUAL SPLIT-SCREEN"
    is_merged: bool = False  # True if this scene reuses another scene's generated image
    merged_with: int | None = None  # 0-based index of the target scene
    image_status: ImageStatus = "pending"
    image_file: str | None = None
    flow_src: str | None = None  # Exact Google Flow CDN image URL for 100% reliable tracking
    error: str | None = None
    started_at: str | None = None
    image_hd: bool | None = None  # True = full-res download from Flow, False = thumbnail, None = unknown (old data)
    job_kind: JobKind = "generate"  # "redownload" = fetch the full-res file of an existing Flow image


class Project(BaseModel):
    id: str
    title: str
    topic: str
    core_answer: str = ""
    story_model: str = ""
    format: Format
    duration_sec: int
    style_id: str
    language: str = "Indonesia"
    status: ProjectStatus = "draft"
    test_limit: int | None = None
    scenes: list[Scene] = Field(default_factory=list)
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class CreateProjectIn(BaseModel):
    topic: str
    format: Format = "9:16"
    duration_sec: int = Field(60, ge=10, le=1800)
    scene_count: int | None = Field(None, ge=1, le=200)
    style_id: str = "doodle-stickman"
    language: str = "Indonesia"
    model: str | None = None


class ImportMarkdownIn(BaseModel):
    markdown: str
    title: str | None = None
    format: Format | None = None
    style_id: str = "doodle-stickman"
    auto_confirm: bool = False


class ParseMarkdownPreviewIn(BaseModel):
    markdown: str


class SceneEdit(BaseModel):
    narration: str = ""
    scene_description: str = ""
    title_text: str = ""
    prompt: str = ""
    tag: str = ""
    is_merged: bool = False
    merged_with: int | None = None


class NarrationOptionsIn(BaseModel):
    mode: Literal["shorter", "longer", "simpler", "reword"] | None = None
    instruction: str = ""


class NarrationIn(BaseModel):
    narration: str = Field(min_length=1)


class UpdateDraftIn(BaseModel):
    title: str
    core_answer: str = ""
    scenes: list[SceneEdit]


class JobResultIn(BaseModel):
    image_base64: str
    mime: str = "image/png"
    flow_src: str | None = None
    note: str | None = None  # e.g. "low resolution: download menu failed"


class JobResultFileIn(BaseModel):
    path: str  # absolute path of the file Chrome downloaded
    note: str | None = None


class JobFailIn(BaseModel):
    error: str = "unknown error"
