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
        if g_info.get("group_size", 1) > 1:
            g_scenes = g_info.get("group_scenes", [idx])
            first_idx = g_scenes[0]
            out["sentence_group_audio"] = f"audio/scene_{first_idx + 1:03d}_group.wav"
            out["sentence_group_key"] = p.scenes[first_idx].group_audio_key or p.scenes[first_idx].audio_key or ""
            out["sentence_group_duration"] = round(sum((p.scenes[si].audio_duration or 0.0) for si in g_scenes), 3)
            all_done = all(p.scenes[si].audio_status == "done" for si in g_scenes)
            any_gen = any(p.scenes[si].audio_status == "generating" for si in g_scenes)
            any_q = any(p.scenes[si].audio_status == "queued" for si in g_scenes)
            any_fail = any(p.scenes[si].audio_status == "failed" for si in g_scenes)
            out["sentence_group_status"] = "done" if all_done else ("generating" if any_gen else ("queued" if any_q else ("failed" if any_fail else "pending")))
    return data
