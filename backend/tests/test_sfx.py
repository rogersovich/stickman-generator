import io
import json
import shutil
import wave

import pytest
from fastapi.testclient import TestClient

from app import capcut_service, config, sfx, storage
from app.main import app
from app.models import Project, Scene

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def wav_bytes(seconds: float, rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(seconds * rate))
    return buf.getvalue()


@pytest.fixture(autouse=True)
def dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SFX_DIR", tmp_path / "sfx")
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path / "output")


@pytest.fixture
def client():
    return TestClient(app)


def make_project(n=3) -> Project:
    p = Project(id="sfx-test", title="SFX", topic="t", format="16:9", duration_sec=30, style_id="doodle-stickman",
                status="done", scenes=[Scene(narration=f"n{i}") for i in range(n)])
    storage.save(p)
    return p


def test_catalog_lists_builtins_with_files():
    items = sfx.list_catalog()
    whoosh = next(i for i in items if i["id"] == "whoosh")
    assert whoosh["built_in"] and whoosh["duration"] > 0 and 0 <= whoosh["volume"] <= 1
    assert all(sfx.path(i["id"]).is_file() for i in items)
    labels = [i["label"].casefold() for i in items]
    assert labels == sorted(labels)


def test_update_volume_and_label_persist():
    sfx.update("bonk", label="Bonk!", volume=1.7)
    item = next(i for i in sfx.list_catalog() if i["id"] == "bonk")
    assert item["label"] == "Bonk!" and item["volume"] == 1.0
    assert json.loads((config.SFX_DIR / "meta.json").read_text())["volumes"]["bonk"] == 1.0


def test_unknown_or_unsafe_id_rejected():
    with pytest.raises(LookupError):
        sfx.update("../etc", volume=0.5)
    assert sfx.get("nope") is None


@needs_ffmpeg
def test_custom_upload_and_delete():
    item = sfx.add_custom(wav_bytes(1.0), "[x] Ding Dong.mp3")
    assert item["label"] == "Ding Dong" and not item["built_in"]
    assert sfx.path(item["id"]).is_file()
    sfx.delete_custom(item["id"])
    assert sfx.get(item["id"]) is None
    with pytest.raises(ValueError):
        sfx.delete_custom("whoosh")  # built-ins cannot be deleted


@needs_ffmpeg
def test_custom_upload_rejects_too_long():
    with pytest.raises(ValueError, match="30 detik"):
        sfx.add_custom(wav_bytes(31.0), "long.wav")


def test_scene_sfx_route(client):
    make_project()
    r = client.put("/api/projects/sfx-test/scenes/1/sfx", json={"sfx_id": "whoosh", "sfx_pos": "end"})
    assert r.status_code == 200
    s = r.json()["scenes"][1]
    assert (s["sfx_id"], s["sfx_pos"]) == ("whoosh", "end")
    assert client.put("/api/projects/sfx-test/scenes/1/sfx", json={"sfx_id": "nope"}).status_code == 400
    assert client.put("/api/projects/sfx-test/scenes/9/sfx", json={"sfx_id": "whoosh"}).status_code == 404
    r = client.put("/api/projects/sfx-test/scenes/1/sfx", json={"sfx_id": None})
    assert r.json()["scenes"][1]["sfx_id"] is None


def test_sfx_routes(client):
    assert any(i["id"] == "whoosh" for i in client.get("/api/sfx").json())
    assert client.get("/api/sfx/whoosh/audio").headers["content-type"] == "audio/wav"
    assert client.get("/api/sfx/nope/audio").status_code == 404
    assert client.patch("/api/sfx/whoosh", json={"volume": 0.4}).json()["volume"] == 0.4


def test_capcut_export_places_sfx_on_own_lane(monkeypatch):
    p = make_project(3)
    d = storage.project_dir(p.id)
    (d / "images").mkdir(parents=True)
    for i, s in enumerate(p.scenes):
        (d / f"images/{i}.png").write_bytes(b"x")
        s.image_status, s.image_file, s.audio_duration = "done", f"images/{i}.png", 4.0
    p.scenes[0].sfx_id = "whoosh"
    p.scenes[2].sfx_id, p.scenes[2].sfx_pos = "bonk", "end"
    storage.save(p)

    captured = {}

    class FakeGen:
        def __init__(self, projects_dir=None):
            pass

        def create_draft(self, **kw):
            captured.update(kw)
            return str(d / "draft")

    monkeypatch.setattr(capcut_service, "CapCutDraftGenerator", FakeGen)
    res = capcut_service.export_project_to_capcut(p.id)
    lane2 = [t for t in captured["audio_tracks"] if t.get("lane") == 2]
    assert [t["path"].name for t in lane2] == ["whoosh.wav", "bonk.wav"]
    assert lane2[0]["start_s"] == 0.0
    bonk_dur = sfx.duration("bonk")
    assert lane2[1]["start_s"] == pytest.approx(12.0 - min(bonk_dur, 4.0))
    assert res["exported_sfx"] == 2

    captured.clear()
    capcut_service.export_project_to_capcut(p.id, include_sfx=False)
    assert not [t for t in captured["audio_tracks"] if t.get("lane") == 2]
