import io

import numpy as np
import pytest
import soundfile as sf

from audio import concat, to_wav_bytes, trim_silence

SR = 24000


def tone(seconds: float, amp: float = 0.5) -> np.ndarray:
    t = np.arange(int(seconds * SR)) / SR
    return (amp * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def silence(seconds: float) -> np.ndarray:
    return np.zeros(int(seconds * SR), dtype=np.float32)


def test_trim_silence_keeps_margin():
    wave = np.concatenate([silence(0.5), tone(1.0), silence(0.5)])
    out = trim_silence(wave, SR)
    assert len(out) / SR == pytest.approx(1.1, abs=0.02)


def test_trim_silence_all_quiet_returns_input():
    wave = silence(1.0)
    assert len(trim_silence(wave, SR)) == len(wave)


def test_concat_crossfade_length():
    out = concat([tone(1.0), tone(1.0)], SR, crossfade_s=0.05)
    assert len(out) / SR == pytest.approx(1.95, abs=0.001)


def test_concat_single_wave_unchanged():
    w = tone(0.3)
    assert np.array_equal(concat([w], SR), w)


def test_to_wav_bytes_roundtrip():
    data = to_wav_bytes(tone(0.5), SR)
    assert data[:4] == b"RIFF"
    back, sr = sf.read(io.BytesIO(data))
    assert sr == SR and len(back) == int(0.5 * SR)
