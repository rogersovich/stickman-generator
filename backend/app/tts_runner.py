#!/usr/bin/env python3
"""Standalone runner for VoxCPM2 LoRA audio generation in Stickman Generator.
Executed via the ML virtualenv (.venv-ml) with PyTorch & CUDA.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Aktifkan optimasi VoxCPM2 terbaik
os.environ["VOXCPM_OPTIMIZE"] = "true"
os.environ["VOXCPM_STUDIO_CLEAN"] = "true"
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

ROOT = Path(__file__).resolve().parent.parent.parent
MANHWA_ROOT = Path(r"D:\Coding\Python\manhwa-recap-studio")

if str(MANHWA_ROOT) not in sys.path:
    sys.path.insert(0, str(MANHWA_ROOT))
if str(MANHWA_ROOT / "worker-ml") not in sys.path:
    sys.path.insert(0, str(MANHWA_ROOT / "worker-ml"))

import numpy as np
import soundfile as sf
from engines.tts_engine import VoxCPM2Narrator

# Import konfigurasi suara
sys.path.insert(0, str(ROOT / "backend"))
from app.voices import get_voice

def save_project_atomic(project_path: Path, data: dict):
    tmp = project_path.parent / "project.json.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(project_path)

def main():
    parser = argparse.ArgumentParser(description="Stickman Generator TTS Runner")
    parser.add_argument("--project_dir", required=True, help="Path ke folder project")
    parser.add_argument("--voice_id", default="suara-1", help="ID suara yang digunakan")
    parser.add_argument("--scene_index", type=int, default=None, help="Generate hanya scene spesifik (0-indexed)")
    parser.add_argument("--force", action="store_true", help="Generate ulang scene yang sudah done")
    args = parser.parse_args()

    project_dir = Path(args.project_dir).resolve()
    project_json_path = project_dir / "project.json"

    if not project_json_path.exists():
        print(f"[Error] File {project_json_path} tidak ditemukan!", file=sys.stderr)
        sys.exit(1)

    with open(project_json_path, "r", encoding="utf-8") as f:
        project_data = json.load(f)

    voice = get_voice(args.voice_id)
    scenes = project_data.get("scenes", [])

    # Tentukan index scene yang perlu di-generate
    target_indices = []
    if args.scene_index is not None:
        if 0 <= args.scene_index < len(scenes):
            target_indices.append(args.scene_index)
    else:
        for i, s in enumerate(scenes):
            narration = (s.get("narration") or "").strip()
            if not narration:
                continue
            if args.force or s.get("audio_status") != "done":
                target_indices.append(i)

    if not target_indices:
        print("[TTS] Tidak ada scene yang perlu di-generate.")
        project_data["voice_status"] = "idle"
        save_project_atomic(project_json_path, project_data)
        sys.exit(0)

    # Tandai status generating awal
    project_data["voice_id"] = voice.id
    project_data["voice_status"] = "generating"
    project_data["voice_error"] = None
    for idx in target_indices:
        scenes[idx]["audio_status"] = "generating"
        scenes[idx]["audio_error"] = None
    save_project_atomic(project_json_path, project_data)

    try:
        print(f"[TTS] Memuat model VoxCPM2 dengan {voice.name} (LoRA: {voice.lora_scale}x, Steps: {voice.inference_timesteps})...")
        t0 = time.perf_counter()
        narrator = VoxCPM2Narrator(local_only=True, lora_path=voice.lora_path)
        narrator.set_lora_scale(voice.lora_scale)
        narrator.set_reference(voice.reference_wav, voice.reference_text)
        print(f"[TTS] Model siap dalam {time.perf_counter() - t0:.2f} detik.")

        print(f"[TTS] Mengompilasi Prompt Cache referensi audio...")
        prompt_cache = narrator.model.tts_model.build_prompt_cache(reference_wav_path=voice.reference_wav)

        for i, idx in enumerate(target_indices, 1):
            scene = scenes[idx]
            narration = (scene.get("narration") or "").strip()
            if not narration:
                continue

            target_text = narration
            if not target_text.endswith((".", "!", "?")):
                target_text += "."

            print(f"\n[TTS] [{i}/{len(target_indices)}] Memproses Scene #{idx+1}: \"{target_text[:60]}...\"")
            scene["audio_status"] = "generating"
            save_project_atomic(project_json_path, project_data)

            t_gen = time.perf_counter()
            gen_res = narrator.model.tts_model._generate_with_prompt_cache(
                target_text=target_text,
                prompt_cache=prompt_cache,
                min_len=2,
                max_len=2000,
                inference_timesteps=voice.inference_timesteps,
                cfg_value=voice.cfg_value,
                retry_badcase=False
            )
            wav, _, _ = next(gen_res)
            audio_arr = np.asarray(wav.squeeze().cpu().numpy(), dtype=np.float32)
            gen_dur = time.perf_counter() - t_gen

            out_filename = f"scene_{idx + 1:03d}.wav"
            out_file = project_dir / out_filename
            sf.write(str(out_file), audio_arr, voice.sample_rate)

            # Upload audio to Cloudflare R2 if configured
            try:
                from app import config, r2
                if config.has_r2():
                    r2.upload_file(out_file, f"projects/{project_dir.name}/{out_filename}")
            except Exception:
                pass

            audio_len_s = len(audio_arr) / float(voice.sample_rate)
            scene["audio_file"] = out_filename
            scene["audio_status"] = "done"
            scene["audio_error"] = None
            save_project_atomic(project_json_path, project_data)

            # Sync project status to D1
            try:
                from app import config, d1
                from app.models import Project
                if config.has_d1():
                    d1.save_project(Project.model_validate(project_data))
            except Exception:
                pass

            print(f"[TTS] [OK] Scene #{idx+1} selesai ({audio_len_s:.2f}s audio dalam {gen_dur:.2f}s) -> {out_filename}")

        project_data["voice_status"] = "done"
        save_project_atomic(project_json_path, project_data)
        print("\n[TTS] Seluruh generasi narasi selesai dengan sukses!")

    except Exception as e:
        err_msg = str(e)
        print(f"[TTS Error] Terjadi kesalahan: {err_msg}", file=sys.stderr)
        project_data["voice_status"] = "failed"
        project_data["voice_error"] = err_msg[:500]
        for idx in target_indices:
            if scenes[idx].get("audio_status") == "generating":
                scenes[idx]["audio_status"] = "failed"
                scenes[idx]["audio_error"] = err_msg[:200]
        save_project_atomic(project_json_path, project_data)
        sys.exit(1)

if __name__ == "__main__":
    main()

