from . import audio, jobs
from .models import Project


def project_out(p: Project) -> dict:
    """Project as JSON, plus derived per-scene info: real image resolution, low-res thumbnail, stale audio, and sentence grouping."""
    data = p.model_dump()
    groups = audio.get_sentence_groups(p.scenes)
    group_map = {}
    for g_idx, g in enumerate(groups):
        for pos, idx in enumerate(g):
            group_map[idx] = {
                "group_id": g_idx,
                "group_size": len(g),
                "group_index": pos,
                "group_first": pos == 0,
                "group_last": pos == len(g) - 1,
                "group_scenes": g,
            }
    for idx, (scene, out) in enumerate(zip(p.scenes, data["scenes"])):
        out["needs_hd"] = jobs.needs_hd(p.id, scene)
        out["image_res"] = jobs.image_res(p.id, scene)
        out["audio_stale"] = audio.is_stale(p, scene)
        g_info = group_map.get(idx, {})
        out["sentence_group"] = g_info.get("group_id", idx)
        out["sentence_group_size"] = g_info.get("group_size", 1)
        out["sentence_group_first"] = g_info.get("group_first", True)
        out["sentence_group_last"] = g_info.get("group_last", True)
        out["sentence_group_scenes"] = g_info.get("group_scenes", [idx])
    return data

