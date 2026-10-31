import io
import zipfile
from fastapi.testclient import TestClient
from app.main import app
from app import storage
from app.models import Project, Scene

client = TestClient(app)

def test_get_voices():
    res = client.get("/api/voices")
    assert res.status_code == 200
    voices = res.json()
    assert isinstance(voices, list)
    suara1 = next((v for v in voices if v["id"] == "suara-1"), None)
    assert suara1 is not None
    assert suara1["name"] == "Suara 1"
    assert suara1["speed"] == 1.0

    suara2 = next((v for v in voices if v["id"] == "suara-2"), None)
    assert suara2 is not None
    assert suara2["name"] == "Suara 2"
    assert suara2["speed"] == 0.9


def test_update_voice_speed():
    res = client.put("/api/voices/suara-2/speed", json={"speed": 0.88})
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == "suara-2"
    assert data["speed"] == 0.88

    res2 = client.get("/api/voices")
    suara2 = next((v for v in res2.json() if v["id"] == "suara-2"), None)
    assert suara2["speed"] == 0.88

    # Reset back to 0.9
    client.put("/api/voices/suara-2/speed", json={"speed": 0.9})

def test_project_audio_flow(tmp_path, monkeypatch):
    p = Project(
        id="test-voice-proj",
        title="Test Audio Project",
        topic="test topic",
        format="9:16",
        duration_sec=60,
        style_id="doodle-stickman",
        scenes=[
            Scene(narration="Halo ini suara stickman satu", scene_description="test 1"),
            Scene(narration="Adegan kedua cerita stickman", scene_description="test 2"),
        ]
    )
    storage.save(p)

    # 1. Trigger generate project audio
    res = client.post(f"/api/projects/{p.id}/generate-audio?voice_id=suara-1")
    assert res.status_code in (200, 409)

    # 2. Stop audio
    res_stop = client.post(f"/api/projects/{p.id}/stop-audio")
    assert res_stop.status_code == 200
    assert res_stop.json()["voice_status"] == "idle"

    # 3. Simulate existing audio file and test ZIP inclusion
    p_dir = storage.project_dir(p.id)
    fake_wav = p_dir / "scene_001.wav"
    fake_wav.write_bytes(b"RIFFdummywavdata")
    
    loaded = storage.load(p.id)
    loaded.scenes[0].audio_file = "scene_001.wav"
    loaded.scenes[0].audio_status = "done"
    storage.save(loaded)

    # Test download zip
    dl_res = client.get(f"/api/projects/{p.id}/download")
    assert dl_res.status_code == 200
    assert dl_res.headers["content-type"] == "application/zip"
    
    with zipfile.ZipFile(io.BytesIO(dl_res.content), "r") as z:
        names = z.namelist()
        assert "scene_001.wav" in names
        assert "project.json" in names
        assert "narration.txt" in names

    # Clean up test project directory
    import shutil
    shutil.rmtree(p_dir, ignore_errors=True)

