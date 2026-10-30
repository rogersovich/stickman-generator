from . import audio, jobs
from .models import Project


def project_out(p: Project) -> dict:
    """Project as JSON, plus derived per-scene info: real image resolution, low-res thumbnail, stale audio."""
    data = p.model_dump()
    for scene, out in zip(p.scenes, data["scenes"]):
        out["needs_hd"] = jobs.needs_hd(p.id, scene)
        out["image_res"] = jobs.image_res(p.id, scene)
        out["audio_stale"] = audio.is_stale(p, scene)
    return data
