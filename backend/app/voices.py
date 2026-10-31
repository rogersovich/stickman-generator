"""Voice configuration registry for Stickman Generator."""

from pathlib import Path
from pydantic import BaseModel

VOICES_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "voices"
CHECKPOINTS_DIR = Path(__file__).resolve().parent.parent.parent / "checkpoints"
MANHWA_DIR = Path(r"D:\Coding\Python\manhwa-recap-studio")

class VoiceConfig(BaseModel):
    id: str
    name: str
    description: str
    lora_path: str
    reference_wav: str
    reference_text: str
    lora_scale: float = 0.7
    inference_timesteps: int = 8
    cfg_value: float = 2.5
    sample_rate: int = 48000
    is_default: bool = False

DEFAULT_VOICE_ID = "suara-1"

VOICE_REGISTRY: dict[str, VoiceConfig] = {
    "suara-1": VoiceConfig(
        id="suara-1",
        name="Suara 1",
        description="Narator Stickman (LoRA 0.7x, Timesteps 8, Karakter Suara Alami)",
        lora_path=str(CHECKPOINTS_DIR / "lora_stickman_voice" / "latest"),
        reference_wav=str(VOICES_DIR / "suara-1" / "reference.wav"),
        reference_text="Umurmu 18 tahun, suratnya datang bulan Maret 1943, ibumu menangis, ayahmu diam saja, dia ikut perang yang pertama, dia tahu apa arti surat itu.",
        lora_scale=0.7,
        inference_timesteps=8,
        cfg_value=2.5,
        sample_rate=48000,
        is_default=True,
    )
}

def get_voice(voice_id: str | None = None) -> VoiceConfig:
    if not voice_id or voice_id not in VOICE_REGISTRY:
        return VOICE_REGISTRY[DEFAULT_VOICE_ID]
    return VOICE_REGISTRY[voice_id]

def list_voices() -> list[dict]:
    return [
        {
            "id": v.id,
            "name": v.name,
            "description": v.description,
            "is_default": v.is_default,
            "lora_scale": v.lora_scale,
            "timesteps": v.inference_timesteps,
        }
        for v in VOICE_REGISTRY.values()
    ]

