"""Whisper-based pronunciation and transcription consistency auditing for generated TTS audio."""

import difflib
import re
from pathlib import Path

def num_to_words_id(n: int) -> str:
    """Convert number to Indonesian words (0-999)."""
    if n == 0:
        return "nol"
    satuan = ["", "satu", "dua", "tiga", "empat", "lima", "enam", "tujuh", "delapan", "sembilan", "sepuluh", "sebelas"]
    if n < 12:
        return satuan[n]
    elif n < 20:
        return satuan[n - 10] + " belas"
    elif n < 100:
        return satuan[n // 10] + " puluh" + ((" " + satuan[n % 10]) if n % 10 != 0 else "")
    elif n < 200:
        return "seratus" + ((" " + num_to_words_id(n - 100)) if n > 100 else "")
    elif n < 1000:
        return satuan[n // 100] + " ratus" + ((" " + num_to_words_id(n % 100)) if n % 100 != 0 else "")
    return str(n)


COLLOQUIAL_MAP = {
    "kalo": "kalau",
    "tau": "tahu",
    "sorry": "sore",
}


def clean_token(w: str) -> str:
    w = re.sub(r"[^\w]", "", w).strip().lower()
    return COLLOQUIAL_MAP.get(w, w)


def tokenize(text: str) -> list[str]:
    raw_tokens = re.findall(r"[a-zA-Z]+|\d+", text.lower())
    result = []
    for t in raw_tokens:
        if t.isdigit():
            words = num_to_words_id(int(t)).split()
            result.extend(words)
        else:
            t = COLLOQUIAL_MAP.get(t, t)
            result.append(t)
    return result


def normalize_stream(text: str) -> str:
    tokens = tokenize(text)
    return "".join(tokens)


def audit_transcription(target_text: str, transcribed_text: str) -> dict:
    """Compare target narration text with Whisper transcription to catch pronunciation errors, missing words, and hallucinations."""
    t_words = tokenize(target_text)
    a_words = tokenize(transcribed_text)

    if not t_words:
        return {"score": 1.0, "status": "ok", "issues": [], "transcribed": transcribed_text}

    sm = difflib.SequenceMatcher(None, t_words, a_words)
    issues = []
    matched_words = 0.0

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        t_sub = t_words[i1:i2]
        a_sub = a_words[j1:j2]
        t_str = "".join(t_sub)
        a_str = "".join(a_sub)

        if tag == "equal":
            matched_words += len(t_sub)
        elif tag == "replace":
            # 1. Exact match ignoring spaces/segmentation (e.g. "diatur" vs "di atur")
            if t_str == a_str:
                matched_words += len(t_sub)
                continue

            for tw in t_sub:
                best_w_sim = max((difflib.SequenceMatcher(None, tw, aw).ratio() for aw in a_sub), default=0.0)
                if tw == a_str:
                    best_w_sim = 1.0

                if best_w_sim >= 0.90:
                    matched_words += 1.0
                elif best_w_sim >= 0.75:
                    matched_words += 0.5
                    issues.append(f"Pelafalan '{tw}' terdengar mirip '{' '.join(a_sub)}'")
                else:
                    issues.append(f"Kata '{tw}' salah lafal / tidak terdeteksi")

        elif tag == "delete":
            for tw in t_sub:
                issues.append(f"Kata '{tw}' terlewat")

        elif tag == "insert":
            extra_text = " ".join(a_sub)
            if len(extra_text) > 3:
                issues.append(f"Kata tambahan '{extra_text}'")

    # Check for hallucination / excessive trailing words
    if len(a_words) > len(t_words) * 1.35 and (len(a_words) - len(t_words)) >= 3:
        if not any("tambahan" in issue for issue in issues):
            issues.append("Terdeteksi kata/suara tambahan (halusinasi)")

    score = round(max(0.0, min(1.0, matched_words / len(t_words))), 2)
    status = "warning" if (len(issues) > 0 or score < 0.85) else "ok"

    return {
        "score": score,
        "status": status,
        "issues": issues,
        "transcribed": transcribed_text.strip(),
    }


def audit_audio_file(model, audio_path: str | Path, target_text: str, lang: str = "id") -> dict:
    """Transcribe an audio file using Whisper and run consistency audit against target text."""
    p = Path(audio_path)
    if not p.is_file():
        return {"score": 0.0, "status": "warning", "issues": ["File audio tidak ditemukan"], "transcribed": ""}

    try:
        segments, _ = model.transcribe(str(p), language=lang if lang in ("id", "en") else "id")
        transcribed = " ".join(s.text for s in segments).strip()
        return audit_transcription(target_text, transcribed)
    except Exception as e:
        return {"score": 0.0, "status": "warning", "issues": [f"Audit error: {e}"], "transcribed": ""}
