from app import settings
from app.models import Project, Scene


def test_scene_audio_defaults():
    s = Scene(narration="Halo")
    assert s.audio_status == "pending" and s.audio_file is None and s.audio_key is None


def test_old_project_json_loads_without_audio_fields():
    p = Project.model_validate({"id": "x", "title": "T", "topic": "t", "format": "16:9", "duration_sec": 60,
                                "style_id": "doodle-stickman", "scenes": [{"narration": "a"}]})
    assert p.voice_id is None and p.tts_model is None and p.scenes[0].audio_status == "pending"


def test_tts_settings_defaults():
    s = settings.load()
    assert s.tts_model == "omnivoice" and s.tts_voice_id is None
    assert (s.omnivoice.num_step, s.omnivoice.guidance_scale, s.omnivoice.t_shift) == (16, 3.0, 0.1)
    assert (s.voxcpm2.cfg_value, s.voxcpm2.inference_timesteps, s.voxcpm2.studio_clean) == (2.5, 10, True)


# ---------- audio queue ----------

import io
import threading
import time
import wave

import pytest

from app import audio, config, storage, voices

VOICE_ID = "c" * 32


def _wav_bytes(seconds: float, rate: int = 24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x01\x00" * int(seconds * rate))
    return buf.getvalue()


@pytest.fixture
def proj(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setattr(config, "VOICES_DIR", tmp_path / "voices")
    monkeypatch.setattr(config, "TTS_WORKER_MODE", "local")
    audio._reset_registry()
    d = tmp_path / "voices" / VOICE_ID
    d.mkdir(parents=True)
    (d / "ref.wav").write_bytes(_wav_bytes(3.0, 48000))
    (d / "meta.json").write_text(voices.Voice(id=VOICE_ID, name="Senandika", transcript="halo", duration=3.0,
                                              created_at="2026-10-30").model_dump_json())
    s = settings.load()
    s.tts_voice_id = VOICE_ID
    settings.save(s)
    p = Project(id="guru-honorer", title="Guru", topic="t", format="16:9", duration_sec=60, style_id="doodle-stickman",
                status="done", scenes=[Scene(narration=f"Kalimat {i}.") for i in range(3)])
    storage.save(p)
    return p


def _scene(i, pid="guru-honorer"):
    return storage.load(pid).scenes[i]


def test_lang_code():
    assert (audio.lang_code("Indonesia"), audio.lang_code("English"), audio.lang_code("Jawa")) == ("id", "en", "id")


def test_enqueue_missing_then_claim_returns_job(proj):
    p = audio.enqueue(proj.id, "missing")
    assert [s.audio_status for s in p.scenes] == ["queued"] * 3
    job = audio.claim("pc", ["omnivoice"], False)
    assert job["scene_index"] == 0 and job["lang"] == "id" and job["text"] == "Kalimat 0."
    assert job["voice_id"] == VOICE_ID and job["voice_transcript"] == "halo" and job["model"] == "omnivoice"
    assert job["params"]["num_step"] == 16 and 1 <= job["seed"] < 2**31
    assert _scene(0).audio_status == "generating"


def test_enqueue_without_voice_raises(proj):
    s = settings.load()
    s.tts_voice_id = None
    settings.save(s)
    with pytest.raises(ValueError, match="Pilih suara dulu"):
        audio.enqueue(proj.id, "missing")


def test_empty_narration_fails_without_queue(proj):
    p = storage.load(proj.id)
    p.scenes[1].narration = "   "
    storage.save(p)
    p = audio.enqueue(proj.id, "missing")
    assert p.scenes[1].audio_status == "failed" and p.scenes[1].audio_error == "Narasi kosong"
    assert [s.audio_status for s in p.scenes] == ["queued", "failed", "queued"]


def test_claim_skips_models_worker_lacks(proj):
    p = storage.load(proj.id)
    p.tts_model = "voxcpm2"
    storage.save(p)
    audio.enqueue(proj.id, "missing")
    assert audio.claim("mac", ["omnivoice"], False) is None
    assert audio.claim("pc", ["omnivoice", "voxcpm2"], False)["model"] == "voxcpm2"


def test_deleted_voice_fails_scene_on_claim(proj):
    audio.enqueue(proj.id, "missing")
    voices.delete(VOICE_ID)
    assert audio.claim("pc", ["omnivoice"], False) is None
    assert {(s.audio_status, s.audio_error) for s in storage.load(proj.id).scenes} == {("failed", "Suara tidak ditemukan")}


def test_save_result_sets_duration_and_file(proj):
    audio.enqueue(proj.id, "missing")
    job = audio.claim("pc", ["omnivoice"], False)
    audio.save_result(proj.id, 0, "pc", job["key"], _wav_bytes(2.5))
    s = _scene(0)
    assert (s.audio_status, s.audio_file, s.audio_duration) == ("done", "audio/scene_001.wav", 2.5)
    assert (config.OUTPUT_DIR / proj.id / "audio" / "scene_001.wav").is_file()
    assert not audio.is_stale(storage.load(proj.id), s)


def test_save_result_rejects_non_wav_and_foreign_worker(proj):
    audio.enqueue(proj.id, "missing")
    job = audio.claim("pc", ["omnivoice"], False)
    with pytest.raises(ValueError):
        audio.save_result(proj.id, 0, "pc", job["key"], b"not a wav")
    with pytest.raises(PermissionError):
        audio.save_result(proj.id, 0, "other", job["key"], _wav_bytes(1.0))


def test_narration_edit_during_generation_is_stale(proj):
    audio.enqueue(proj.id, "missing")
    job = audio.claim("pc", ["omnivoice"], False)
    p = storage.load(proj.id)
    p.scenes[0].narration = "Teks baru."
    storage.save(p)
    p = audio.save_result(proj.id, 0, "pc", job["key"], _wav_bytes(1.0))
    assert p.scenes[0].audio_status == "done" and audio.is_stale(p, p.scenes[0])


def test_voice_change_makes_done_audio_stale(proj):
    audio.enqueue(proj.id, "missing", [0])
    job = audio.claim("pc", ["omnivoice"], False)
    audio.save_result(proj.id, 0, "pc", job["key"], _wav_bytes(1.0))
    p = storage.load(proj.id)
    p.tts_model = "voxcpm2"
    assert audio.is_stale(p, p.scenes[0])


def test_missing_mode_requeues_only_pending_failed_stale(proj):
    audio.enqueue(proj.id, "missing", [0])
    job = audio.claim("pc", ["omnivoice"], False)
    audio.save_result(proj.id, 0, "pc", job["key"], _wav_bytes(1.0))
    p = audio.enqueue(proj.id, "missing")
    assert [s.audio_status for s in p.scenes] == ["done", "queued", "queued"]
    p = audio.enqueue(proj.id, "all")
    assert [s.audio_status for s in p.scenes] == ["queued", "queued", "queued"]


def test_regenerate_uses_new_seed(proj, monkeypatch):
    seeds = iter([1, 2])
    monkeypatch.setattr(audio.random, "randint", lambda a, b: next(seeds))
    audio.enqueue(proj.id, "all", [0])
    j1 = audio.claim("pc", ["omnivoice"], False)
    audio.save_result(proj.id, 0, "pc", j1["key"], _wav_bytes(1.0))
    audio.enqueue(proj.id, "all", [0])
    j2 = audio.claim("pc", ["omnivoice"], False)
    assert (j1["seed"], j2["seed"]) == (1, 2)


def test_reap_requeues_expired_lease(proj, monkeypatch):
    audio.enqueue(proj.id, "missing", [0])
    job = audio.claim("pc", ["omnivoice"], False)
    now = time.time()
    monkeypatch.setattr(audio.time, "time", lambda: now + 121)
    assert audio.reap() == 1
    assert _scene(0).audio_status == "queued"
    with pytest.raises(PermissionError):
        audio.save_result(proj.id, 0, "pc", job["key"], _wav_bytes(1.0))


def test_heartbeat_extends_lease(proj, monkeypatch):
    audio.enqueue(proj.id, "missing", [0])
    audio.claim("pc", ["omnivoice"], False)
    now = time.time()
    monkeypatch.setattr(audio.time, "time", lambda: now + 100)
    audio.heartbeat("pc", ["omnivoice"], "CUDA", False)
    monkeypatch.setattr(audio.time, "time", lambda: now + 200)
    assert audio.reap() == 0


def test_reset_on_startup(proj):
    audio.enqueue(proj.id, "missing")
    audio.claim("pc", ["omnivoice"], False)
    audio._reset_registry()
    assert audio.reset_on_startup() == 1
    assert _scene(0).audio_status == "queued"


def test_concurrent_claims_never_share_scene(proj):
    audio.enqueue(proj.id, "missing")
    got = []
    threads = [threading.Thread(target=lambda n=n: got.append(audio.claim(f"w{n}", ["omnivoice"], False))) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    jobs = [(j["project_id"], j["scene_index"]) for j in got if j]
    assert len(jobs) == 3 and len(set(jobs)) == 3


def test_auto_mode_local_skips_models_of_online_remote(proj, monkeypatch):
    monkeypatch.setattr(config, "TTS_WORKER_MODE", "auto")
    audio.enqueue(proj.id, "missing")
    audio.heartbeat("pc", ["omnivoice"], "CUDA", False)
    assert audio.claim("mac", ["omnivoice"], True) is None
    assert audio.claim("pc", ["omnivoice"], False)["scene_index"] == 0
    monkeypatch.setattr(config, "TTS_WORKER_MODE", "remote")
    audio._reset_registry()
    assert audio.claim("mac", ["omnivoice"], True) is None


def test_workers_status_reports_online(proj, monkeypatch):
    audio.heartbeat("pc", ["omnivoice", "voxcpm2"], "CUDA · RTX 3060", False)
    [w] = audio.workers_status()
    assert (w["name"], w["device"], w["local"], w["online"]) == ("pc", "CUDA · RTX 3060", False, True)
    now = time.time()
    monkeypatch.setattr(audio.time, "time", lambda: now + 31)
    assert audio.workers_status()[0]["online"] is False


def test_pause_unqueues(proj):
    audio.enqueue(proj.id, "missing")
    p = audio.pause(proj.id)
    assert [s.audio_status for s in p.scenes] == ["pending"] * 3
