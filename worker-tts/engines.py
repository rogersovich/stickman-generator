"""TTS engines: OmniVoice (k2-fsa) and VoxCPM2 (OpenBMB), both cloning a reference voice.

Ported from manhwa-recap-studio/worker-ml/engines/tts_engine.py, keeping its hard-won memory rules
and dropping what this app doesn't use (LoRA, singing, Whisper, speed stretching for VoxCPM2).
"""

import contextlib
import importlib.util
import io
import os
from pathlib import Path

import numpy as np

import settings
from device import free_memory, pick_device

OMNIVOICE_REPO = "k2-fsa/OmniVoice"
OMNIVOICE_FILES = ["config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json",
                   "chat_template.jinja", "audio_tokenizer/config.json",
                   "audio_tokenizer/model.safetensors", "audio_tokenizer/preprocessor_config.json"]
VOXCPM2_REPO = "openbmb/VoxCPM2"
VOXCPM2_FILES = ["config.json", "model.safetensors", "audiovae.pth", "special_tokens_map.json",
                 "tokenizer.json", "tokenizer_config.json"]
MODEL_FILES = {"omnivoice": (OMNIVOICE_REPO, OMNIVOICE_FILES), "voxcpm2": (VOXCPM2_REPO, VOXCPM2_FILES)}
MODEL_PACKAGES = {"omnivoice": "omnivoice", "voxcpm2": "voxcpm"}


def installed_models() -> list[str]:
    return [m for m, pkg in MODEL_PACKAGES.items() if importlib.util.find_spec(pkg) is not None]


def snapshot_dir(model_id: str) -> Path:
    """Download (or find in the cache) every file of a model and return its snapshot folder."""
    from huggingface_hub import hf_hub_download

    repo, files = MODEL_FILES[model_id]
    paths = [Path(hf_hub_download(repo_id=repo, filename=f, cache_dir=settings.HF_CACHE)) for f in files]
    top = paths[0].parent  # config.json sits at the snapshot root
    return top


@contextlib.contextmanager
def _quiet():
    """The model libraries print progress bars per sentence; keep the worker log readable."""
    with open(os.devnull, "w") as null, contextlib.redirect_stdout(null), contextlib.redirect_stderr(io.StringIO()):
        yield


def _seed(torch, seed: int) -> None:
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)


class OmniVoiceEngine:
    model_id = "omnivoice"
    sr = 24000

    def __init__(self):
        import torch

        self.torch = torch
        self.device = pick_device()
        # fp16 on MPS falls back to CPU for some ops; fp32 is a bit slower but stable and fits 8 GB
        self.dtype = torch.float16 if self.device.startswith("cuda") else torch.float32
        self.model = None
        self._prompt = None
        self._ref = None

    def load(self) -> None:
        from omnivoice import OmniVoice

        snapshot = snapshot_dir(self.model_id)
        with _quiet():
            self.model = OmniVoice.from_pretrained(str(snapshot), device_map=self.device, dtype=self.dtype)

    def set_reference(self, ref_wav: Path, transcript: str) -> None:
        # encode the reference once and reuse it for every scene with this voice
        if self._ref == (str(ref_wav), transcript):
            return
        with _quiet():
            self._prompt = self.model.create_voice_clone_prompt(ref_audio=str(ref_wav), ref_text=transcript.strip() or None)
        self._ref = (str(ref_wav), transcript)

    def generate(self, text: str, seed: int, params: dict, lang: str) -> np.ndarray:
        _seed(self.torch, seed)
        speed = float(params.get("speed", 1.0))
        with _quiet(), self.torch.inference_mode():
            out = self.model.generate(
                text=text,
                language=lang,
                voice_clone_prompt=self._prompt,
                speed=speed if abs(speed - 1.0) > 0.01 else None,
                num_step=int(params.get("num_step", 16)),
                guidance_scale=float(params.get("guidance_scale", 3.0)),
                t_shift=float(params.get("t_shift", 0.1)),
                class_temperature=0.0,
                position_temperature=5.0,
            )
        if not out or out[0] is None or len(out[0]) == 0:
            raise RuntimeError("OmniVoice tidak menghasilkan audio")
        free_memory(self.device)
        return np.asarray(out[0], dtype=np.float32).reshape(-1)

    def unload(self) -> None:
        self.model = self._prompt = self._ref = None
        free_memory(self.device)


def studio_clean_master(audio: np.ndarray, sr: int = 48000) -> np.ndarray:
    """Remove VoxCPM2's 12 kHz+ vocoder hiss and gate the noise floor between words, keeping the peak level."""
    if len(audio) == 0:
        return audio
    from scipy import signal

    orig_peak = float(np.max(np.abs(audio)))
    if orig_peak < 1e-6:
        return audio
    cleaned = signal.sosfilt(signal.butter(2, 12000, "low", fs=sr, output="sos"), audio)
    thresh = 10 ** (-28.0 / 20.0)
    frame = int(sr * 0.01)
    gains = np.ones(len(cleaned), dtype=np.float32)
    curr = 1.0
    for st in range(0, len(cleaned), frame):
        chunk = cleaned[st:st + frame]
        rms = float(np.sqrt(np.mean(chunk**2))) if len(chunk) else 0.0
        curr = curr * 0.75 + (1.0 if rms >= thresh else 0.05) * 0.25
        gains[st:st + frame] = curr
    out = cleaned * gains
    new_peak = float(np.max(np.abs(out)))
    if new_peak > 1e-6:
        out = out * (orig_peak / new_peak)
    return out.astype(np.float32)


def apply_speed(audio: np.ndarray, speed: float, sr: int) -> np.ndarray:
    """Change tempo without altering pitch using ffmpeg atempo."""
    speed = float(speed)
    if abs(speed - 1.0) <= 0.02 or len(audio) == 0:
        return audio
    import subprocess
    try:
        proc = subprocess.run(
            [
                "ffmpeg", "-y", "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", "pipe:0",
                "-filter:a", f"atempo={speed}", "-f", "f32le", "-ar", str(sr), "-ac", "1", "pipe:1"
            ],
            input=audio.tobytes(),
            capture_output=True,
            check=True
        )
        if proc.stdout:
            return np.frombuffer(proc.stdout, dtype=np.float32)
    except Exception as e:
        print(f"[worker-tts] warning: ffmpeg atempo failed ({e}), keeping original audio", flush=True)
    return audio

class VoxCPM2Engine:
    model_id = "voxcpm2"
    sr = 48000

    def __init__(self):
        import torch

        self.torch = torch
        self.device = pick_device()
        if self.device.startswith("cuda"):
            torch.set_float32_matmul_precision("high")
            torch.backends.cuda.matmul.allow_tf32 = True
            torch.backends.cudnn.allow_tf32 = True
        self.model = None
        self.is_optimized = False
        self._ref_wav = None
        self._current_lora = None
        self._current_lora_scale = 1.0

    def load(self) -> None:
        # Load safetensors on the CPU first: loading straight to the GPU duplicates ~9 GB in VRAM (OOM / "invalid
        # python storage" on Windows).
        try:
            import voxcpm.model.voxcpm2 as v2

            if not getattr(v2, "_safe_load_patched", False):
                orig = v2.load_file

                def load_on_cpu(*args, **kwargs):
                    if "device" in kwargs:
                        kwargs["device"] = "cpu"
                    elif len(args) >= 2:
                        args = (args[0], "cpu") + args[2:]
                    return orig(*args, **kwargs)

                v2.load_file = load_on_cpu
                v2._safe_load_patched = True
        except Exception:
            pass
        from voxcpm import VoxCPM

        snapshot = str(snapshot_dir(self.model_id))
        optimize = settings.VOXCPM_OPTIMIZE and self.device.startswith("cuda")
        if optimize and importlib.util.find_spec("triton") is None:
            print("[voxcpm2] VOXCPM_OPTIMIZE=true but triton is not installed: running unoptimized")
            optimize = False
        try:
            with _quiet():
                self.model = VoxCPM.from_pretrained(snapshot, load_denoiser=False, optimize=optimize)
            self.is_optimized = optimize
        except Exception as e:
            if not optimize:
                raise
            print(f"[voxcpm2] torch.compile failed ({e}); falling back to unoptimized")
            free_memory(self.device)
            with _quiet():
                self.model = VoxCPM.from_pretrained(snapshot, load_denoiser=False, optimize=False)

    def set_reference(self, ref_wav: Path, transcript: str) -> None:
        self._ref_wav = str(ref_wav)  # VoxCPM2 clones from audio only; the transcript is not used

    def set_lora_scale(self, scale: float = 1.0) -> None:
        scale_f = float(scale)
        self._current_lora_scale = scale_f
        if hasattr(self.model, "tts_model") and hasattr(self.model.tts_model, "_iter_lora_modules"):
            for m in self.model.tts_model._iter_lora_modules():
                if hasattr(m, "_base_scaling") and hasattr(m, "scaling"):
                    m.scaling.fill_(m._base_scaling * scale_f)

    def set_lora(self, lora_path: str | None, scale: float = 0.7) -> None:
        if not lora_path or not Path(lora_path).exists():
            return
        if getattr(self, "_current_lora", None) == str(lora_path):
            self.set_lora_scale(scale)
            return
        try:
            self.model.tts_model.load_lora_weights(str(lora_path))
            self._current_lora = str(lora_path)
            self.set_lora_scale(scale)
            print(f"[voxcpm2] LoRA dimuat dari {lora_path} (scale: {scale:.2f}x)", flush=True)
        except Exception as e:
            print(f"[voxcpm2] Gagal memuat LoRA '{lora_path}': {e}", flush=True)

    def generate(self, text: str, seed: int, params: dict, lang: str) -> np.ndarray:
        _seed(self.torch, seed)
        with _quiet(), self.torch.inference_mode():
            wav = self.model.generate(
                text=text,
                reference_wav_path=self._ref_wav,
                cfg_value=float(params.get("cfg_value", 2.5)),
                inference_timesteps=int(params.get("inference_timesteps", 10)),
            )
        if wav is None or len(wav) == 0:
            raise RuntimeError("VoxCPM2 tidak menghasilkan audio")
        arr = np.asarray(wav, dtype=np.float32).reshape(-1)
        speed = float(params.get("speed", 1.0))
        if abs(speed - 1.0) > 0.02:
            arr = apply_speed(arr, speed, self.sr)
        if params.get("studio_clean", True):
            arr = studio_clean_master(arr, self.sr)
        # With CUDA graphs alive, empty_cache() crashes Windows (0xC0000005): only free memory when not compiled
        if not self.is_optimized:
            free_memory(self.device)
        return arr

    def unload(self) -> None:
        self.model = self._ref_wav = self._current_lora = None
        free_memory(self.device)  # safe now: the compiled graphs went away with the model


ENGINES = {"omnivoice": OmniVoiceEngine, "voxcpm2": VoxCPM2Engine}
_current = None


def get_engine(model_id: str):
    """One model in memory at a time (8 GB Macs can't hold both)."""
    global _current
    if _current is not None and _current.model_id == model_id and _current.model is not None:
        return _current
    unload_current()
    engine = ENGINES[model_id]()
    engine.load()
    _current = engine
    return engine


def unload_current() -> None:
    global _current
    if _current is not None:
        _current.unload()
        _current = None
