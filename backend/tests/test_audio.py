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
