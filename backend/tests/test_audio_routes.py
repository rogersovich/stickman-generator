import base64
import io
import shutil
import wave
import zipfile

import pytest
from fastapi.testclient import TestClient

from app import audio, config, main, storage
from app.models import Project, Scene

LOCAL = ("127.0.0.1", 50000)
TAILNET = ("100.101.1.2", 50000)


def wav_bytes(seconds: float, rate: int = 24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x01\x00" * int(seconds * rate))
    return buf.getvalue()


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setattr(config, "VOICES_DIR", tmp_path / "voices")
    monkeypatch.setattr(config, "TTS_WORKER_MODE", "local")
    monkeypatch.setattr(config, "TTS_WORKER_TOKEN", "")
    audio._reset_registry()
    voice_id = "d" * 32
    d = tmp_path / "voices" / voice_id
    d.mkdir(parents=True)
    (d / "ref.wav").write_bytes(wav_bytes(3.0, 48000))
    (d / "meta.json").write_text(
        f'{{"id": "{voice_id}", "name": "Ghaisan", "transcript": "", "duration": 3.0, "created_at": "x"}}'
    )
    p = Project(id="proj-a", title="A", topic="t", format="16:9", duration_sec=60, style_id="doodle-stickman",
                status="done", scenes=[Scene(narration="Satu."), Scene(narration="Dua.")])
    storage.save(p)
    return {"voice_id": voice_id, "project_id": p.id}


def client(addr=LOCAL):
    return TestClient(main.app, client=addr)


def _generate(c, env):
    assert c.put(f"/api/projects/{env['project_id']}/tts", json={"voice_id": env["voice_id"], "tts_model": None}).status_code == 200
    r = c.post(f"/api/projects/{env['project_id']}/audio/generate", json={"mode": "missing"})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_voice_crud_roundtrip(env):
    c = client()
    body = {"name": "Baru", "transcript": "halo", "audio_base64": base64.b64encode(wav_bytes(3.0)).decode(), "filename": "a.wav"}
    v = c.post("/api/voices", json=body).json()
    assert v["name"] == "Baru"
    assert v["id"] in [x["id"] for x in c.get("/api/voices").json()]
    assert c.get(f"/api/voices/{v['id']}/audio").status_code == 200
    assert c.delete(f"/api/voices/{v['id']}").status_code == 204
    assert c.get(f"/api/voices/{v['id']}/audio").status_code == 404


def test_generate_then_worker_cycle(env):
    c = client()
    p = _generate(c, env)
    assert [s["audio_status"] for s in p["scenes"]] == ["queued", "queued"]
    r = c.post("/api/tts-worker/claim", json={"name": "mac", "models": ["omnivoice"], "device": "MPS"})
    job = r.json()
    assert job["scene_index"] == 0 and job["text"] == "Satu."
    assert c.get(f"/api/tts-worker/voices/{job['voice_id']}/audio").status_code == 200
    r = c.put(f"/api/tts-worker/jobs/{job['project_id']}/0/result", params={"key": job["key"]},
              content=wav_bytes(1.5), headers={"X-Worker-Name": "mac", "Content-Type": "audio/wav"})
    assert r.status_code == 204, r.text
    s = c.get(f"/api/projects/{env['project_id']}").json()["scenes"][0]
    assert (s["audio_status"], s["audio_duration"], s["audio_stale"]) == ("done", 1.5, False)
    assert c.get(f"/files/{env['project_id']}/audio/scene_001.wav").status_code == 200
    st = c.get("/api/tts/status").json()
    assert st["queued"] == 1 and st["workers"][0]["name"] == "mac"


def test_worker_fail_and_foreign_result(env):
    c = client()
    _generate(c, env)
    job = c.post("/api/tts-worker/claim", json={"name": "mac", "models": ["omnivoice"]}).json()
    r = c.put(f"/api/tts-worker/jobs/{job['project_id']}/0/result", params={"key": job["key"]},
              content=wav_bytes(1.0), headers={"X-Worker-Name": "other"})
    assert r.status_code == 409
    r = c.post(f"/api/tts-worker/jobs/{job['project_id']}/0/fail", json={"error": "CUDA OOM"}, headers={"X-Worker-Name": "mac"})
    assert r.status_code == 204
    s = c.get(f"/api/projects/{env['project_id']}").json()["scenes"][0]
    assert (s["audio_status"], s["audio_error"]) == ("failed", "CUDA OOM")


def test_generate_without_voice_is_400(env):
    r = client().post(f"/api/projects/{env['project_id']}/audio/generate", json={"mode": "missing"})
    assert r.status_code == 400 and "Pilih suara" in r.json()["detail"]


def test_claim_with_nothing_queued_is_204(env):
    assert client().post("/api/tts-worker/claim", json={"name": "mac", "models": ["omnivoice"]}).status_code == 204


def test_remote_worker_needs_token(env, monkeypatch):
    hello = {"name": "pc", "models": ["omnivoice"]}
    assert client(TAILNET).post("/api/tts-worker/claim", json=hello).status_code == 404
    monkeypatch.setattr(config, "TTS_WORKER_TOKEN", "s3cret")
    c = client(TAILNET)
    assert c.post("/api/tts-worker/claim", json=hello).status_code == 401
    assert c.post("/api/tts-worker/claim", json=hello, headers={"Authorization": "Bearer nope"}).status_code == 401
    assert c.post("/api/tts-worker/claim", json=hello, headers={"Authorization": "Bearer s3cret"}).status_code == 204
    assert audio.workers_status()[0]["local"] is False


def test_untrusted_network_blocked(env, monkeypatch):
    monkeypatch.setattr(config, "TTS_WORKER_TOKEN", "s3cret")
    c = client(("203.0.113.5", 1))
    assert c.get("/api/projects").status_code == 403
    r = c.post("/api/tts-worker/claim", json={"name": "pc", "models": ["omnivoice"]}, headers={"Authorization": "Bearer s3cret"})
    assert r.status_code == 204
    assert client(TAILNET).get("/api/projects").status_code == 200


def test_zip_includes_audio(env):
    c = client()
    _generate(c, env)
    job = c.post("/api/tts-worker/claim", json={"name": "mac", "models": ["omnivoice"]}).json()
    c.put(f"/api/tts-worker/jobs/{job['project_id']}/0/result", params={"key": job["key"]},
          content=wav_bytes(1.0), headers={"X-Worker-Name": "mac"})
    z = zipfile.ZipFile(io.BytesIO(c.get(f"/api/projects/{env['project_id']}/download").content))
    assert "audio/scene_001.wav" in z.namelist()


def test_import_legacy_missing_db_is_404(env, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LEGACY_STUDIO_DB", tmp_path / "nope.db")
    r = client().post("/api/voices/import-legacy")
    assert r.status_code == 404 and "tidak ditemukan" in r.json()["detail"]
