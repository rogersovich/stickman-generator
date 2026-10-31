"""CLI script to audit all existing audio scenes in a project using Whisper."""

import sys
import os
import json
from pathlib import Path

# Add paths
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir / "backend"))
sys.path.insert(0, str(root_dir / "worker-tts"))

from app import storage
import audit as tts_audit
import splitter

def audit_project(project_id: str, indices: list[int] | None = None) -> dict:
    p = storage.load(project_id)
    if not p:
        print(f"Project '{project_id}' not found")
        return {"error": "Project not found"}

    p_dir = storage.project_dir(project_id)
    model = splitter.get_whisper()
    lang = getattr(p, "language", "id") or "id"

    target_indices = indices if indices is not None else list(range(len(p.scenes)))
    audited_count = 0
    warnings_count = 0

    print(f"Auditing {len(target_indices)} scenes in project '{project_id}'...")

    for i in target_indices:
        if i < 0 or i >= len(p.scenes):
            continue
        s = p.scenes[i]
        if not s.audio_file or s.audio_status != "done":
            continue

        wav_path = p_dir / s.audio_file
        if not wav_path.is_file():
            continue

        try:
            segments, _ = model.transcribe(str(wav_path), language=lang if lang in ("id", "en") else "id")
            transcribed = " ".join(seg.text for seg in segments).strip()
            res = tts_audit.audit_transcription(s.narration, transcribed)

            s.audio_audit_score = res["score"]
            s.audio_audit_status = res["status"]
            s.audio_audit_text = res["transcribed"]
            s.audio_audit_issues = res["issues"]

            audited_count += 1
            if res["status"] == "warning":
                warnings_count += 1
                print(f"  [!] Scene #{i+1} WARNING ({res['score']*100:.0f}%): {', '.join(res['issues'])}")
            else:
                print(f"  [OK] Scene #{i+1} ({res['score']*100:.0f}%)")
        except Exception as e:
            print(f"  [Error] Scene #{i+1}: {e}")

    storage.save(p)
    print(f"Audit completed: {audited_count} scenes audited, {warnings_count} warnings found.")
    return {
        "audited": audited_count,
        "warnings": warnings_count,
    }

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python audit_cli.py <project_id> [scene_indices...]")
        sys.exit(1)
    pid = sys.argv[1]
    idxs = [int(x) for x in sys.argv[2:]] if len(sys.argv) > 2 else None
    audit_project(pid, idxs)

