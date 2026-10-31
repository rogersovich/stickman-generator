"""Small numpy helpers: join model outputs, trim silence, encode WAV."""

import io

import numpy as np
import soundfile as sf


def concat(waves: list[np.ndarray], sr: int, crossfade_s: float = 0.05) -> np.ndarray:
    """Join pieces with a short linear crossfade so sentence boundaries don't click."""
    out = np.asarray(waves[0], dtype=np.float32)
    n = int(crossfade_s * sr)
    for w in waves[1:]:
        w = np.asarray(w, dtype=np.float32)
        k = min(n, len(out), len(w))
        if k == 0:
            out = np.concatenate([out, w])
            continue
        ramp = np.linspace(0.0, 1.0, k, dtype=np.float32)
        mixed = out[-k:] * (1 - ramp) + w[:k] * ramp
        out = np.concatenate([out[:-k], mixed, w[k:]])
    return out


def trim_silence(wave: np.ndarray, sr: int, threshold_db: float = -45.0, margin_s: float = 0.05) -> np.ndarray:
    """Cut leading/trailing silence (frames quieter than threshold_db below full scale), keeping a small margin."""
    if not len(wave):
        return wave
    frame = max(1, int(0.01 * sr))
    n_frames = len(wave) // frame
    if n_frames == 0:
        return wave
    frames = np.abs(wave[: n_frames * frame]).reshape(n_frames, frame).max(axis=1)
    loud = np.nonzero(frames > 10 ** (threshold_db / 20))[0]
    if not len(loud):
        return wave
    margin = int(margin_s * sr)
    start = max(0, loud[0] * frame - margin)
    end = min(len(wave), (loud[-1] + 1) * frame + margin)
    return wave[start:end]


def to_wav_bytes(wave: np.ndarray, sr: int) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, np.clip(wave, -1.0, 1.0), sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()
