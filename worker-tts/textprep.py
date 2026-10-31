"""Turn a scene's narration into the text pieces the TTS model reads."""

import re

from num2words import num2words

END_PUNCT = (".", "!", "?", ",", ";", ":", '"', "'", "…")
# "3.000.000" is three million in Indonesian; English writes "3,000,000"
_THOUSANDS = {"id": r"\d{1,3}(?:\.\d{3})+", "en": r"\d{1,3}(?:,\d{3})+"}
_DECIMAL_SEP = {"id": ",", "en": "."}


def normalize_numbers(text: str, lang: str) -> str:
    """Spell out numbers so the model doesn't guess how to read them."""
    thousands = _THOUSANDS.get(lang, _THOUSANDS["id"])
    dec = re.escape(_DECIMAL_SEP.get(lang, ","))

    def spell(m: re.Match) -> str:
        raw = m.group(0)
        if re.fullmatch(thousands, raw):
            return num2words(int(re.sub(r"[.,]", "", raw)), lang=lang)
        if re.search(dec, raw):
            whole, frac = re.split(dec, raw, maxsplit=1)
            return num2words(float(f"{whole}.{frac}"), lang=lang)
        return num2words(int(raw), lang=lang)

    return re.sub(rf"{thousands}|\d+(?:{dec}\d+)?", spell, text)


def _split_long(sentence: str, max_chars: int) -> list[str]:
    pieces = []
    while len(sentence) > max_chars:
        window = sentence[: max_chars + 1]
        cut = max(window.rfind(", "), window.rfind("; "))
        cut = cut + 1 if cut > 0 else window.rfind(" ")
        if cut <= 0:
            cut = max_chars
        pieces.append(sentence[:cut].strip())
        sentence = sentence[cut:].strip()
    if sentence:
        pieces.append(sentence)
    return pieces


def split_sentences(text: str, max_chars: int = 200) -> list[str]:
    """Split into sentence groups of at most max_chars, never cutting inside a word."""
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    sentences = []
    for s in re.split(r"(?<=[.!?…])\s+", text):
        sentences.extend(_split_long(s, max_chars))
    pieces: list[str] = []
    for s in sentences:
        if pieces and len(pieces[-1]) + 1 + len(s) <= max_chars:
            pieces[-1] = f"{pieces[-1]} {s}"
        else:
            pieces.append(s)
    return pieces


def prepare(text: str, lang: str, model: str) -> list[str]:
    pieces = split_sentences(normalize_numbers(text, lang))
    if model == "voxcpm2":
        # VoxCPM2 hallucinates extra words after an unfinished sentence; never add "..." though
        pieces = [p if p.endswith(END_PUNCT) else f"{p}." for p in pieces]
    return pieces
