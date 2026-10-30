"""Service for exporting a Stickman project directly to CapCut Desktop drafts."""

import re
import time
from pathlib import Path
from typing import Optional

from . import storage
from .capcut import CapCutDraftGenerator


def export_project_to_capcut(
    project_id: str,
    drafts_dir: Optional[str] = None,
    project_name: Optional[str] = None,
    ken_burns: bool = True,
    enable_zoom: bool = True,
    enable_pan: bool = True,
    zoom_ratio: float = 1.15,
    enable_transitions: bool = True,
    transition_duration: float = 0.5,
    allowed_transitions: Optional[list[str]] = None,
) -> dict:
    p = storage.load(project_id)
    if not p:
        raise LookupError(f"Project '{project_id}' tidak ditemukan")

    p_dir = storage.project_dir(project_id)

    image_items = []
    audio_tracks = []
    current_time_s = 0.0

    for i, s in enumerate(p.scenes):
        img_path = (p_dir / s.image_file) if s.image_file else None
        audio_path = (p_dir / s.audio_file) if s.audio_file else None

        dur = float(s.audio_duration) if (s.audio_duration and s.audio_duration > 0.1) else 2.5

        if img_path and img_path.exists():
            image_items.append({
                "path": img_path,
                "duration": dur,
                "chapter": f"Scene {i+1}",
            })

        if audio_path and audio_path.exists():
            audio_tracks.append({
                "path": audio_path,
                "duration": dur,
                "start_s": current_time_s,
                "chapter": f"Scene {i+1}",
            })

        current_time_s += dur

    if not image_items:
        raise ValueError("Belum ada file gambar yang selesai di project ini untuk diekspor ke CapCut")

    gen = CapCutDraftGenerator(projects_dir=drafts_dir)

    base_name = project_name.strip() if project_name and project_name.strip() else (p.title or p.id)
    safe_name = re.sub(r'[\\/*?:"<>|]', "", base_name).strip() or p.id
    # Clean draft name with date-time suffix
    draft_name = f"{safe_name}_{time.strftime('%Y%m%d_%H%M%S')}"
    ratio = p.format if p.format in ("16:9", "9:16") else "16:9"

    draft_path = gen.create_draft(
        project_name=draft_name,
        image_paths=image_items,
        ratio=ratio,
        ken_burns=ken_burns,
        enable_zoom=enable_zoom,
        enable_pan=enable_pan,
        zoom_ratio=zoom_ratio,
        canvas_blur=True,
        enable_transitions=enable_transitions,
        transition_duration=transition_duration,
        allowed_transitions=allowed_transitions,
        audio_tracks=audio_tracks,
    )

    # Generate an optional .srt subtitle file next to the draft for easy CapCut caption import
    srt_path = Path(draft_path) / f"{draft_name}.srt"
    try:
        _write_srt(p.scenes, srt_path)
    except Exception:
        pass

    # Persist export options and draft record into project
    result = {
        "status": "success",
        "draft_name": draft_name,
        "draft_path": str(draft_path),
        "total_scenes": len(p.scenes),
        "exported_images": len(image_items),
        "exported_audios": len(audio_tracks),
        "total_duration_s": round(current_time_s, 2),
    }

    try:
        p.export_opts = {
            "ken_burns": ken_burns,
            "enable_zoom": enable_zoom,
            "enable_pan": enable_pan,
            "zoom_ratio": zoom_ratio,
            "enable_transitions": enable_transitions,
            "transition_duration": transition_duration,
            "allowed_transitions": allowed_transitions,
        }
        p.last_capcut_draft = result
        storage.save(p)
    except Exception:
        pass

    return result


def _format_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _write_srt(scenes, srt_path: Path) -> None:
    current = 0.0
    entries = []
    idx = 1
    for s in scenes:
        dur = float(s.audio_duration) if (s.audio_duration and s.audio_duration > 0.1) else 2.5
        text = (s.narration or "").strip()
        if text:
            start_str = _format_srt_time(current)
            end_str = _format_srt_time(current + dur)
            entries.append(f"{idx}\n{start_str} --> {end_str}\n{text}\n")
            idx += 1
        current += dur
    if entries:
        srt_path.write_text("\n".join(entries), encoding="utf-8")
