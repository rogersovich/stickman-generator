"""Whisper-based word alignment and audio splitting for sentence-grouped TTS.

Takes a combined audio wave for multiple scenes (one full sentence) and slices it
cleanly at scene boundaries using word timestamps, energy-minimum search, and micro-fades.
"""

import difflib
import io
import re
import wave
from pathlib import Path
import numpy as np
import soundfile as sf
import torch

_whisper_instance = None

DIGIT_MAP = {
    "0": "nol", "1": "satu", "2": "dua", "3": "tiga", "4": "empat",
    "5": "lima", "6": "enam", "7": "tujuh", "8": "delapan", "9": "sembilan", "10": "sepuluh"
}


def get_whisper():
    global _whisper_instance
    if _whisper_instance is None:
        import faster_whisper
        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if device == "cuda" else "int8"
        _whisper_instance = faster_whisper.WhisperModel("base", device=device, compute_type=compute_type)
    return _whisper_instance


def clean_token(w: str) -> str:
    w = re.sub(r"[^\w\s]", "", w).strip().lower()
    return DIGIT_MAP.get(w, w)


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[\w]+", text.lower())
    return [DIGIT_MAP.get(t, t) for t in tokens if t]


def find_best_cut_point(audio: np.ndarray, sr: int, end_t: float, start_t: float) -> float:
    """Find the optimal cut timestamp between two words.

    If there is a clear pause (>= 80ms), cut in the middle.
    If the pause is small or words touch, search a short window around end_t
    for the local RMS minimum to avoid cutting active phonemes.
    """
    total_dur = len(audio) / sr
    gap = start_t - end_t
    if gap >= 0.08:
        return (end_t + start_t) / 2.0

    search_start = max(0.0, end_t - 0.03)
    search_end = min(total_dur, max(start_t + 0.02, end_t + 0.06))

    start_samp = int(search_start * sr)
    end_samp = int(search_end * sr)
    if end_samp <= start_samp + 10:
        return min(total_dur, (end_t + start_t) / 2.0 if start_t > end_t else end_t + 0.02)

    window = audio[start_samp:end_samp]
    frame_len = max(1, int(sr * 0.005))  # 5ms window
    if len(window) > frame_len:
        energies = np.convolve(np.abs(window), np.ones(frame_len) / frame_len, mode="valid")
        min_idx = int(np.argmin(energies))
        best_samp = start_samp + min_idx + frame_len // 2
        return min(total_dur, best_samp / sr)

    return min(total_dur, (end_t + start_t) / 2.0 if start_t > end_t else end_t + 0.02)


def slice_with_fades(audio: np.ndarray, sr: int, cuts: list[float], fade_in_ms: float = 15, fade_out_ms: float = 25) -> list[np.ndarray]:
    """Slice audio at cut timestamps and apply micro-fades to eliminate clicks."""
    slices = []
    fade_in_samples = int(sr * fade_in_ms / 1000)
    fade_out_samples = int(sr * fade_out_ms / 1000)

    for i in range(len(cuts) - 1):
        start_samp = max(0, int(cuts[i] * sr))
        end_samp = min(len(audio), int(cuts[i + 1] * sr))
        if end_samp <= start_samp:
            end_samp = min(len(audio), start_samp + int(sr * 0.1))

        clip = audio[start_samp:end_samp].copy()

        # Apply smooth fade in
        if len(clip) > fade_in_samples:
            fade_in = np.linspace(0.0, 1.0, fade_in_samples, dtype=clip.dtype)
            clip[:fade_in_samples] *= fade_in

        # Apply smooth fade out
        if len(clip) > fade_out_samples:
            fade_out = np.linspace(1.0, 0.0, fade_out_samples, dtype=clip.dtype)
            clip[-fade_out_samples:] *= fade_out

        slices.append(clip)
    return slices


def fallback_proportional_slice(audio: np.ndarray, sr: int, scene_texts: list[str]) -> list[np.ndarray]:
    """Fallback slice based on character counts if alignment fails."""
    lengths = [max(1, len(t.strip())) for t in scene_texts]
    total_len = sum(lengths)
    total_dur = len(audio) / sr
    cuts = [0.0]
    accum = 0.0
    for l in lengths[:-1]:
        accum += (l / total_len) * total_dur
        cuts.append(accum)
    cuts.append(total_dur)
    return slice_with_fades(audio, sr, cuts)


def align_and_slice(audio: np.ndarray, sr: int, scene_texts: list[str], lang: str = "id") -> list[np.ndarray]:
    """Align whisper word timestamps to scene texts and split the combined audio."""
    if len(scene_texts) <= 1:
        return [audio]

    total_dur = len(audio) / sr

    # Write audio to in-memory WAV buffer for faster-whisper
    buf = io.BytesIO()
    sf.write(buf, audio, sr, format="WAV")
    buf.seek(0)

    try:
        model = get_whisper()
        segments, _ = model.transcribe(
            buf,
            language=lang if lang in ("id", "en") else "id",
            word_timestamps=True,
            vad_filter=True,
        )

        whisper_words = []
        for seg in segments:
            for w in seg.words:
                cleaned = clean_token(w.word)
                if cleaned:
                    whisper_words.append({
                        "word": cleaned,
                        "raw": w.word.strip(),
                        "start": w.start,
                        "end": w.end,
                    })

        if not whisper_words:
            print("[splitter] Whisper did not detect words, using fallback slice", flush=True)
            return fallback_proportional_slice(audio, sr, scene_texts)

        # Build target tokens with scene indices
        target_tokens = []
        for s_idx, text in enumerate(scene_texts):
            tokens = tokenize(text)
            for t in tokens:
                target_tokens.append((t, s_idx))

        if not target_tokens:
            return fallback_proportional_slice(audio, sr, scene_texts)

        transcribed_tokens = [w["word"] for w in whisper_words]

        # Use SequenceMatcher to find alignment
        matcher = difflib.SequenceMatcher(None, [t[0] for t in target_tokens], transcribed_tokens)
        opcodes = matcher.get_opcodes()

        target_to_whisper = {}
        for tag, i1, i2, j1, j2 in opcodes:
            if tag == "equal":
                for idx in range(i2 - i1):
                    target_to_whisper[i1 + idx] = j1 + idx
            elif tag == "replace":
                for idx in range(min(i2 - i1, j2 - j1)):
                    target_to_whisper[i1 + idx] = j1 + idx

        # Determine cut points between scenes
        cut_points = [0.0]
        prev_cut = 0.0

        for s_idx in range(len(scene_texts) - 1):
            s_token_indices = [i for i, (_, s) in enumerate(target_tokens) if s == s_idx]
            next_s_token_indices = [i for i, (_, s) in enumerate(target_tokens) if s == s_idx + 1]

            # Find last matched whisper word for current scene
            last_w_idx = None
            for ti in reversed(s_token_indices):
                if ti in target_to_whisper:
                    last_w_idx = target_to_whisper[ti]
                    break

            # Find first matched whisper word for next scene
            first_w_idx = None
            for ti in next_s_token_indices:
                if ti in target_to_whisper:
                    first_w_idx = target_to_whisper[ti]
                    break

            if last_w_idx is not None and first_w_idx is not None:
                end_t = whisper_words[last_w_idx]["end"]
                start_t = whisper_words[first_w_idx]["start"]
                cut = find_best_cut_point(audio, sr, end_t, start_t)
            elif last_w_idx is not None:
                cut = min(total_dur - 0.1, whisper_words[last_w_idx]["end"] + 0.05)
            elif first_w_idx is not None:
                cut = max(0.1, whisper_words[first_w_idx]["start"] - 0.05)
            else:
                # Proportional estimate between previous cut and end
                remaining_scenes = len(scene_texts) - s_idx
                cut = prev_cut + (total_dur - prev_cut) / remaining_scenes

            # Ensure strictly monotonic cuts
            cut = max(prev_cut + 0.1, min(total_dur - 0.1, cut))
            cut_points.append(cut)
            prev_cut = cut

        cut_points.append(total_dur)
        return slice_with_fades(audio, sr, cut_points)

    except Exception as e:
        print(f"[splitter] Alignment error: {e}, using fallback slice", flush=True)
        return fallback_proportional_slice(audio, sr, scene_texts)

