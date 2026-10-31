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


def normalize_chars(text: str) -> str:
    tokens = re.findall(r"[\w]+", text.lower())
    expanded = [DIGIT_MAP.get(t, t) for t in tokens if t]
    return "".join(re.sub(r"[^\w]", "", t) for t in expanded)


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

        # Build cumulative clean character streams for target scenes and whisper words
        scene_char_ends = []
        target_clean = ""
        for t in scene_texts:
            c = normalize_chars(t)
            target_clean += c
            scene_char_ends.append(len(target_clean))

        if not target_clean:
            return fallback_proportional_slice(audio, sr, scene_texts)

        whisper_clean = ""
        whisper_spans = []
        for w in whisper_words:
            c = normalize_chars(w["word"])
            st = len(whisper_clean)
            whisper_clean += c
            en = len(whisper_clean)
            whisper_spans.append((st, en, w))

        if not whisper_clean:
            return fallback_proportional_slice(audio, sr, scene_texts)

        # Match character streams using SequenceMatcher (immune to word-splitting/compounding variations)
        matcher = difflib.SequenceMatcher(None, target_clean, whisper_clean)
        opcodes = matcher.get_opcodes()

        def t2w(t_idx: int) -> int:
            for tag, i1, i2, j1, j2 in opcodes:
                if i1 <= t_idx <= i2:
                    if tag == "equal":
                        return j1 + (t_idx - i1)
                    elif tag == "replace":
                        ratio = (t_idx - i1) / max(1, i2 - i1)
                        return int(j1 + ratio * (j2 - j1))
                    elif tag == "delete":
                        return j1
                    elif tag == "insert":
                        return j2
            return len(whisper_clean)

        # Determine cut points between scenes
        cut_points = [0.0]
        prev_cut = 0.0

        for s_idx in range(len(scene_texts) - 1):
            target_boundary = scene_char_ends[s_idx]
            whisper_boundary = t2w(target_boundary)

            prev_w = None
            next_w = None
            spanning_w = None

            for st, en, w in whisper_spans:
                if en <= whisper_boundary:
                    prev_w = w
                if st >= whisper_boundary and next_w is None:
                    next_w = w
                if st < whisper_boundary < en:
                    spanning_w = w

            if prev_w and next_w:
                end_t = prev_w["end"]
                start_t = next_w["start"]
                cut = find_best_cut_point(audio, sr, end_t, start_t)
            elif spanning_w:
                st, en, w = spanning_w
                ratio = (whisper_boundary - st) / max(1, en - st)
                cut = w["start"] + ratio * (w["end"] - w["start"])
            elif prev_w:
                cut = min(total_dur - 0.1, prev_w["end"] + 0.05)
            elif next_w:
                cut = max(0.1, next_w["start"] - 0.05)
            else:
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

