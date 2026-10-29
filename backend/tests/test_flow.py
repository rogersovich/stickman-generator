import base64

import pytest
from fastapi.testclient import TestClient

from app import config, main
from app.models import Scene
from app.story import StoryDraft, parse_story

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\nfake").decode()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path)

    def fake_story(topic, count, language, style_id, model=None):
        scenes = [Scene(narration=f"n{i}", scene_description=f"d{i}", title_text="T") for i in range(count)]
        return StoryDraft(title="Judul", core_answer="Jawaban", model=model or "default", scenes=scenes)

    monkeypatch.setattr(main, "generate_story", fake_story)
    return TestClient(main.app)


def test_full_flow(client):
    p = client.post("/api/projects", json={"topic": "Kota Bawah Laut", "format": "9:16", "duration_sec": 14}).json()
    assert p["status"] == "draft" and len(p["scenes"]) == 2 and p["core_answer"] == "Jawaban"

    # no jobs while draft
    assert client.get("/api/jobs/next").status_code == 204

    # edit draft
    scenes = [{"narration": "a", "scene_description": "divers", "title_text": "KOTA"}]
    p = client.put(f"/api/projects/{p['id']}", json={"title": "Baru", "core_answer": "Edit", "scenes": scenes}).json()
    assert p["title"] == "Baru" and p["core_answer"] == "Edit" and len(p["scenes"]) == 1

    client.post(f"/api/projects/{p['id']}/confirm")
    job = client.get("/api/jobs/next").json()
    assert job["prompt"].startswith("Create Image:")
    assert "9:16 vertical portrait" in job["prompt"] and '"KOTA"' in job["prompt"]

    # only one job at a time
    assert client.get("/api/jobs/next").status_code == 204

    r = client.post(f"/api/jobs/{p['id']}/0/result", json={"image_base64": "data:image/png;base64," + PNG})
    assert r.status_code == 200
    p = client.get(f"/api/projects/{p['id']}").json()
    assert p["status"] == "done" and p["scenes"][0]["image_file"] == "scene_001.png"
    assert client.get(f"/files/{p['id']}/scene_001.png").status_code == 200
    assert client.get(f"/api/projects/{p['id']}/download").status_code == 200


def test_fail_and_retry(client):
    p = client.post("/api/projects", json={"topic": "x", "scene_count": 1}).json()
    client.post(f"/api/projects/{p['id']}/confirm")
    job = client.get("/api/jobs/next").json()
    client.post(f"/api/jobs/{p['id']}/{job['scene_index']}/fail", json={"error": "no image"})
    assert client.get(f"/api/projects/{p['id']}").json()["status"] == "done"
    client.post(f"/api/projects/{p['id']}/scenes/0/retry")
    assert client.get("/api/jobs/next").status_code == 200


def test_paused_project_gives_no_jobs(client):
    p = client.post("/api/projects", json={"topic": "x", "scene_count": 2}).json()
    client.post(f"/api/projects/{p['id']}/confirm")
    client.post(f"/api/projects/{p['id']}/pause")
    assert client.get("/api/jobs/next").status_code == 204


def test_parse_story_handles_code_fences():
    d = parse_story('```json\n{"core_answer":"C","outline":["x"],"title":"T","scenes":[{"narration":"a","scene_description":"b"}]}\n```')
    assert d.title == "T" and d.core_answer == "C" and d.scenes[0].scene_description == "b" and d.scenes[0].title_text == ""


def test_extract_content_handles_sse():
    from app.story import _extract_content

    sse = (
        'data: {"choices":[{"delta":{"role":"assistant"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"{\\"a\\""}}]}\n\n'
        'data: {"choices":[{"delta":{"content":": 1}"}}]}\n\n'
        "data: [DONE]\n"
    )
    assert _extract_content(sse) == '{"a": 1}'
    assert _extract_content('{"choices":[{"message":{"content":"hi"}}]}') == "hi"


def test_generate_story_falls_back(monkeypatch):
    from app import story

    monkeypatch.setattr(config, "NINEROUTER_MODEL", "main")
    monkeypatch.setattr(config, "NINEROUTER_FALLBACK_MODELS", ["backup"])
    calls = []

    def fake_complete(model, messages):
        calls.append(model)
        if model == "main":
            raise story.StoryError("boom")
        return StoryDraft(title="T", scenes=[Scene(narration="kata " * 17)])

    monkeypatch.setattr(story, "_complete_story", fake_complete)
    assert story.generate_story("x", 1, "Indonesia", "doodle-stickman").title == "T"
    assert calls == ["main", "backup"]


def test_short_narration_triggers_one_rewrite(monkeypatch):
    from app import story

    monkeypatch.setattr(config, "NINEROUTER_MODEL", "main")
    monkeypatch.setattr(config, "NINEROUTER_FALLBACK_MODELS", [])
    replies = [
        StoryDraft(title="T", scenes=[Scene(narration="kata " * 5)]),
        StoryDraft(title="T", scenes=[Scene(narration="kata " * 17)]),
    ]
    monkeypatch.setattr(story, "_complete_story", lambda model, messages: replies.pop(0))
    draft = story.generate_story("x", 1, "Indonesia", "doodle-stickman")
    assert len(draft.scenes[0].narration.split()) == 17 and not replies


def test_model_choice(client, monkeypatch):
    monkeypatch.setattr(config, "NINEROUTER_MODEL_CHOICES", ["a", "b"])
    assert client.get("/api/config").json()["models"] == ["a", "b"]
    p = client.post("/api/projects", json={"topic": "x", "scene_count": 1, "model": "b"}).json()
    assert p["story_model"] == "b"
    assert client.post("/api/projects", json={"topic": "x", "scene_count": 1, "model": "zzz"}).status_code == 400


def test_chosen_model_tried_before_fallbacks(monkeypatch):
    from app import story

    monkeypatch.setattr(config, "NINEROUTER_MODEL", "main")
    monkeypatch.setattr(config, "NINEROUTER_FALLBACK_MODELS", ["backup", "picked"])
    calls = []

    def fake_complete(model, messages):
        calls.append(model)
        raise story.StoryError("boom")

    monkeypatch.setattr(story, "_complete_story", fake_complete)
    with pytest.raises(story.StoryError):
        story.generate_story("x", 1, "Indonesia", "doodle-stickman", "picked")
    assert calls == ["picked", "backup"]


def test_release_puts_scene_back_in_queue(client):
    p = client.post("/api/projects", json={"topic": "x", "scene_count": 2}).json()
    client.post(f"/api/projects/{p['id']}/confirm")
    job = client.get("/api/jobs/next").json()
    client.post(f"/api/jobs/{p['id']}/{job['scene_index']}/release")
    assert client.get(f"/api/projects/{p['id']}").json()["scenes"][0]["image_status"] == "pending"
    assert client.get("/api/jobs/next").json()["scene_index"] == 0


def test_result_file_moves_download(client, tmp_path, monkeypatch):
    downloads = tmp_path / "Downloads"
    (downloads / "stickman-flow").mkdir(parents=True)
    monkeypatch.setattr(config, "DOWNLOADS_DIR", downloads.resolve())
    p = client.post("/api/projects", json={"topic": "x", "scene_count": 1}).json()
    client.post(f"/api/projects/{p['id']}/confirm")
    client.get("/api/jobs/next")
    # a low-res thumbnail saved first, then replaced by the full-res download
    client.post(f"/api/jobs/{p['id']}/0/result", json={"image_base64": PNG, "mime": "image/webp"})
    f = downloads / "stickman-flow" / "scene.png"
    f.write_bytes(b"\x89PNG fullres")
    assert client.post(f"/api/jobs/{p['id']}/0/result-file", json={"path": str(f)}).status_code == 200
    assert not f.exists()
    d = config.OUTPUT_DIR / p["id"]
    assert (d / "scene_001.png").read_bytes() == b"\x89PNG fullres" and not (d / "scene_001.webp").exists()

    outside = tmp_path / "evil.png"
    outside.write_bytes(b"x")
    assert client.post(f"/api/jobs/{p['id']}/0/result-file", json={"path": str(outside)}).status_code == 400


def test_redownload_flow(client, tmp_path, monkeypatch):
    import hashlib

    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    monkeypatch.setattr(config, "DOWNLOADS_DIR", downloads.resolve())
    p = client.post("/api/projects", json={"topic": "x", "scene_count": 2}).json()
    pid = p["id"]
    client.post(f"/api/projects/{pid}/confirm")
    for i in range(2):
        client.get("/api/jobs/next")
        client.post(f"/api/jobs/{pid}/{i}/result", json={"image_base64": PNG, "mime": "image/webp"})
    p = client.get(f"/api/projects/{pid}").json()
    assert p["status"] == "done" and all(s["needs_hd"] for s in p["scenes"])

    p = client.post(f"/api/projects/{pid}/redownload").json()
    assert p["status"] == "generating" and [s["image_status"] for s in p["scenes"]] == ["pending", "pending"]

    job = client.get("/api/jobs/next").json()
    assert job["kind"] == "redownload" and "prompt" not in job
    assert job["thumb_sha256"] == hashlib.sha256(base64.b64decode(PNG)).hexdigest()

    # failure keeps the thumbnail and marks the scene done with a warning
    client.post(f"/api/jobs/{pid}/0/fail", json={"error": "not found"})
    s0 = client.get(f"/api/projects/{pid}").json()["scenes"][0]
    assert s0["image_status"] == "done" and s0["image_file"] and "ambil ulang HD gagal" in s0["error"]

    job = client.get("/api/jobs/next").json()
    f = downloads / "scene.jpg"
    f.write_bytes(b"\xff\xd8 fullres")
    client.post(f"/api/jobs/{pid}/{job['scene_index']}/result-file", json={"path": str(f)})
    p = client.get(f"/api/projects/{pid}").json()
    assert p["status"] == "done"
    assert p["scenes"][1]["image_hd"] is True and p["scenes"][1]["needs_hd"] is False
    assert p["scenes"][1]["image_file"] == "scene_002.jpg"

    # single-scene request works even without needs_hd, retry resets kind to generate
    client.post(f"/api/projects/{pid}/scenes/1/redownload")
    assert client.get("/api/jobs/next").json()["kind"] == "redownload"
    client.post(f"/api/projects/{pid}/scenes/1/retry")
    assert client.get(f"/api/projects/{pid}").json()["scenes"][1]["job_kind"] == "generate"


def test_settings_roundtrip_and_used_by_jobs(client, monkeypatch):
    monkeypatch.setattr(config, "NINEROUTER_MODEL_CHOICES", ["m1", "m2", "gemini/gemini-3.5-flash-lite"])
    s = client.get("/api/settings").json()
    assert s["rewrite_model"] == "gemini/gemini-3.5-flash-lite"
    assert s["tempo_preset"] == "normal" and s["resolution"] == "2K"

    s |= {"default_model": "m2", "seconds_per_scene": 10, "delay_between_images": {"min": 5, "max": 9}}
    assert client.put("/api/settings", json=s).status_code == 200
    assert client.get("/api/config").json()["seconds_per_scene"] == 10

    # 30 s at 10 s/scene -> 3 scenes; the default model comes from settings
    p = client.post("/api/projects", json={"topic": "x", "duration_sec": 30}).json()
    assert len(p["scenes"]) == 3 and p["story_model"] == "m2"
    client.post(f"/api/projects/{p['id']}/confirm")
    job = client.get("/api/jobs/next").json()
    assert (job["delay_min"], job["delay_max"]) == (5, 9) and job["project_title"] == "Judul"

    assert client.put("/api/settings", json=s | {"default_model": "nope"}).status_code == 400
    assert client.put("/api/settings", json=s | {"rewrite_model": "nope"}).status_code == 400
    bad = s | {"delay_between_images": {"min": 9, "max": 1}}
    assert client.put("/api/settings", json=bad).status_code == 422


def test_delete_project(client):
    p = client.post("/api/projects", json={"topic": "x", "scene_count": 1}).json()
    client.post(f"/api/projects/{p['id']}/confirm")
    client.get("/api/jobs/next")  # scene 1 now generating
    assert client.delete(f"/api/projects/{p['id']}").status_code == 409

    client.post(f"/api/jobs/{p['id']}/0/release")
    assert client.delete(f"/api/projects/{p['id']}").status_code == 200
    assert not (config.OUTPUT_DIR / p["id"]).exists()
    assert client.get(f"/api/projects/{p['id']}").status_code == 404
    assert client.delete(f"/api/projects/{p['id']}").status_code == 404
    assert client.delete("/api/projects/..").status_code == 404


def test_narration_options_and_save(client, monkeypatch):
    seen = {}

    def fake_rewrite(**kw):
        seen.update(kw)
        return ["satu", "dua", "tiga"], "m"

    monkeypatch.setattr(main, "rewrite_narration", fake_rewrite)
    p = client.post("/api/projects", json={"topic": "x", "scene_count": 3}).json()
    r = client.post(f"/api/projects/{p['id']}/scenes/1/narration-options", json={"mode": "shorter"}).json()
    assert r == {"options": ["satu", "dua", "tiga"], "model": "m"}
    assert seen["narrations"] == ["n0", "n1", "n2"] and seen["index"] == 1
    assert seen["scene_description"] == "d1" and seen["title"] == "Judul"
    assert seen["language"] == "Indonesia" and seen["mode"] == "shorter"
    assert seen["model"] == "gemini/gemini-3.5-flash-lite"  # rewrite model from settings, not the story model

    bad = client.post(f"/api/projects/{p['id']}/scenes/1/narration-options", json={"mode": "funnier"})
    assert bad.status_code == 422

    # saving works even after confirm (images don't depend on narration)
    client.post(f"/api/projects/{p['id']}/confirm")
    p2 = client.put(f"/api/projects/{p['id']}/scenes/1/narration", json={"narration": " dua "}).json()
    assert p2["scenes"][1]["narration"] == "dua" and p2["status"] == "generating"
    assert client.put(f"/api/projects/{p['id']}/scenes/9/narration", json={"narration": "x"}).status_code == 404


REWRITE_ARGS = dict(
    title="T", topic="t", core_answer="c", language="Indonesia",
    narrations=["A satu", "B " * 18, "C tiga"], index=1, scene_description="img", title_text="CAP",
)


def test_rewrite_narration_prompt_and_fallback(monkeypatch):
    from app import story

    monkeypatch.setattr(config, "NINEROUTER_FALLBACK_MODELS", ["backup"])
    calls = []

    def fake_chat(model, messages, temperature=0.6):
        calls.append(model)
        if model == "main":
            raise story.StoryError("down")
        prompt = messages[1]["content"]
        assert "1. A satu" in prompt and "THE SCENE YOU ARE EDITING" in prompt and "3. C tiga" in prompt
        assert "Its illustration shows: img" in prompt and "11-14 words" in prompt  # 18 words * 0.6-0.78
        ok = "kata " * 12
        return '```json\n{"options": ["%s", "%s", "%s", "extra"]}\n```' % (ok, ok, ok)

    monkeypatch.setattr(story, "_chat", fake_chat)
    opts, model = story.rewrite_narration(**REWRITE_ARGS, mode="shorter", model="main")
    assert len(opts) == 3 and model == "backup" and calls == ["main", "backup"]
    with pytest.raises(story.StoryError):
        story.rewrite_narration(**REWRITE_ARGS, mode=None)


def test_rewrite_retries_once_when_length_is_off(monkeypatch):
    from app import story

    replies = [
        '{"options": ["%s", "%s", "%s"]}' % (("x " * 5,) * 3),   # way too short for "reword" of 18 words
        '{"options": ["%s", "%s", "%s"]}' % (("y " * 18,) * 3),  # fixed
    ]
    monkeypatch.setattr(story, "_chat", lambda model, messages, temperature=0.6: replies.pop(0))
    opts, _ = story.rewrite_narration(**REWRITE_ARGS, mode="reword", model="m")
    assert all(len(o.split()) == 18 for o in opts) and not replies


def test_concurrent_generation_queue(client):
    md = """# Concurrency Test
## Scene 1
Beat narasi: N1
```
CREATE IMAGE
prompt 1
```
## Scene 2
Beat narasi: N2
```
CREATE IMAGE
prompt 2
```
## Scene 3
Beat narasi: N3
```
CREATE IMAGE
prompt 3
```
## Scene 4
Beat narasi: N4
```
CREATE IMAGE
prompt 4
```
"""
    p = client.post("/api/projects/import-markdown", json={"markdown": md, "auto_confirm": True}).json()
    pid = p["id"]

    # Concurrency default is 3: first 3 jobs should be dispatched
    j1 = client.get("/api/jobs/next")
    assert j1.status_code == 200 and j1.json()["scene_index"] == 0
    j2 = client.get("/api/jobs/next")
    assert j2.status_code == 200 and j2.json()["scene_index"] == 1
    j3 = client.get("/api/jobs/next")
    assert j3.status_code == 200 and j3.json()["scene_index"] == 2

    # 4th job should be blocked because concurrency limit of 3 is reached
    assert client.get("/api/jobs/next").status_code == 204

    # Finish job 0 -> releases slot -> next call should return scene 3
    client.post(f"/api/jobs/{pid}/0/result", json={"image_base64": PNG, "mime": "image/png"})
    j4 = client.get("/api/jobs/next")
    assert j4.status_code == 200 and j4.json()["scene_index"] == 3

