import numpy as np
import pytest
import splitter

def test_normalize_chars():
    assert splitter.normalize_chars("Kamu pikir, telat 2 minggu!") == "kamupikirtelatduaminggu"
    assert splitter.normalize_chars("diatur,") == "diatur"

def test_character_stream_alignment_indonesian_prefix():
    texts = [
        "Kamu pikir, telat seminggu atau dua minggu masih bisa diatur,",
        "Tabunganmu masih cukup untuk bensin dan beras."
    ]
    # Simulate Whisper splitting "diatur" into "di" + "atur" and "tabunganmu masih" into "tabungan" + "mumasih"
    whisper_words = [
        {"word": "kamu", "start": 0.0, "end": 0.28},
        {"word": "pikir", "start": 0.28, "end": 0.72},
        {"word": "telat", "start": 1.06, "end": 1.28},
        {"word": "seminggu", "start": 1.28, "end": 1.66},
        {"word": "atau", "start": 1.66, "end": 1.82},
        {"word": "dua", "start": 1.82, "end": 2.08},
        {"word": "minggu", "start": 2.08, "end": 2.40},
        {"word": "masih", "start": 2.40, "end": 2.64},
        {"word": "bisa", "start": 2.64, "end": 2.88},
        {"word": "di", "start": 2.88, "end": 3.02},
        {"word": "atur", "start": 3.02, "end": 3.44},
        {"word": "tabungan", "start": 3.74, "end": 4.10},
        {"word": "mumasih", "start": 4.10, "end": 4.48},
        {"word": "cukup", "start": 4.48, "end": 4.78},
        {"word": "untuk", "start": 4.78, "end": 4.96},
        {"word": "bensin", "start": 4.96, "end": 5.42},
        {"word": "dan", "start": 5.42, "end": 5.60},
        {"word": "beras", "start": 5.60, "end": 5.92},
    ]

    total_dur = 6.0
    sr = 24000
    dummy_audio = np.zeros(int(total_dur * sr), dtype=np.float32)

    # Let's mock get_whisper to return these words directly
    class MockSegment:
        def __init__(self, words):
            self.words = [type('W', (), w) for w in words]

    class MockModel:
        def transcribe(self, *args, **kwargs):
            return [MockSegment(whisper_words)], None

    orig_get_whisper = splitter.get_whisper
    splitter.get_whisper = lambda: MockModel()
    try:
        slices = splitter.align_and_slice(dummy_audio, sr, texts)
        assert len(slices) == 2
        dur1 = len(slices[0]) / sr
        # Cut must be between 'atur' end (3.44) and 'tabungan' start (3.74)
        assert 3.40 <= dur1 <= 3.80, f"Expected cut in [3.40, 3.80], got {dur1}"
    finally:
        splitter.get_whisper = orig_get_whisper

