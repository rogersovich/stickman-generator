"""TTS worker: takes narration jobs from the app, generates one clip per scene, uploads it.

Run: worker-tts/.venv-ml/bin/python worker-tts/main.py   (Windows: worker-tts\\run-worker.bat)
"""

import threading
import time

import settings  # noqa: F401  (sets the Hugging Face cache before anything imports it)
from audio import concat, to_wav_bytes, trim_silence
from client import Client, NotOurs, Offline
from device import describe_device
from engines import get_engine, installed_models, unload_current
from textprep import prepare


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def reference_wav(client: Client, job: dict):
    """Voice reference recordings are cached per (voice, file version)."""
    path = settings.VOICE_CACHE / f"{job['voice_id']}_{job['voice_version']}.wav"
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(client.voice_audio(job["voice_id"]))
    return path


def run_job(client: Client, job: dict, device: str) -> None:
    label = f"[{job['project_id'][:24]} #{job['scene_index'] + 1}]"
    t0 = time.perf_counter()
    engine = get_engine(job["model"])
    engine.set_reference(reference_wav(client, job), job.get("voice_transcript") or "")

    # LoRA integration for VoxCPM2
    lora_target = job.get("lora_path")
    if not lora_target:
        if job.get("voice_id") == "suara-1":
            default_lora = settings.WORKER_DIR.parent / "checkpoints" / "lora_stickman_voice" / "latest"
            if (default_lora / "lora_weights.safetensors").is_file():
                lora_target = str(default_lora)
        elif job.get("voice_id") == "suara-2":
            default_lora = settings.WORKER_DIR.parent / "checkpoints" / "lora_stickman_voice_2" / "latest"
            if (default_lora / "lora_weights.safetensors").is_file():
                lora_target = str(default_lora)
    if hasattr(engine, "set_lora") and lora_target:
        lora_scale = float(job.get("lora_scale") or job.get("params", {}).get("lora_scale", 0.7))
        engine.set_lora(lora_target, lora_scale)

    pieces = prepare(job["text"], job["lang"], job["model"])
    if not pieces:
        raise ValueError("Narasi kosong")
    waves = [engine.generate(p, job["seed"], job["params"], job["lang"]) for p in pieces]
    wave = trim_silence(concat(waves, engine.sr), engine.sr)
    client.put_result(job["project_id"], job["scene_index"], job["key"], to_wav_bytes(wave, engine.sr))
    log(f"{label} {job['model']} {len(wave) / engine.sr:.1f}s audio in {time.perf_counter() - t0:.1f}s ({device})")


def heartbeat_loop(client: Client, models: list[str], device: str, stop: threading.Event) -> None:
    while not stop.wait(settings.HEARTBEAT_SECONDS):
        try:
            client.heartbeat(models, device)
        except Exception:
            pass  # the main loop reports connection problems


def main() -> None:
    models = installed_models()
    if not models:
        raise SystemExit("No TTS model package installed (omnivoice / voxcpm). Run the setup script first.")
    device = describe_device()
    client = Client(settings.SERVER, settings.TOKEN, settings.NAME)
    log(f"TTS worker '{settings.NAME}' · {device} · models: {', '.join(models)} · server {settings.SERVER}")

    stop = threading.Event()
    threading.Thread(target=heartbeat_loop, args=(client, models, device, stop), daemon=True).start()
    last_job = time.time()
    offline = False
    try:
        while True:
            try:
                job = client.claim(models, device)
                if offline:
                    log("backend reachable again")
                    offline = False
            except Offline as e:
                if not offline:
                    log(f"backend offline ({e}); retrying every {settings.OFFLINE_RETRY_SECONDS}s")
                    offline = True
                time.sleep(settings.OFFLINE_RETRY_SECONDS)
                continue
            if not job:
                if time.time() - last_job > settings.IDLE_UNLOAD_SECONDS:
                    unload_current()
                time.sleep(settings.POLL_SECONDS)
                continue
            last_job = time.time()
            try:
                run_job(client, job, device)
            except NotOurs:
                log(f"scene {job['scene_index'] + 1} was reassigned; result dropped")
            except Offline as e:
                log(f"backend offline while uploading ({e}); the scene will be requeued")
            except Exception as e:  # one bad scene must not stop the worker
                log(f"scene {job['scene_index'] + 1} failed: {e}")
                try:
                    client.fail(job["project_id"], job["scene_index"], str(e))
                except Exception:
                    pass
    except KeyboardInterrupt:
        log("stopping")
    finally:
        stop.set()
        unload_current()


if __name__ == "__main__":
    main()
