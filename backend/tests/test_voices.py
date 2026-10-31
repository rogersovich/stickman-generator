import io
import shutil
import sqlite3
import wave

import pytest

from app import config, voices

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def wav_bytes(seconds: float, rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(seconds * rate))
    return buf.getvalue()


@pytest.fixture(autouse=True)
def voices_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "VOICES_DIR", tmp_path / "voices")
    return tmp_path / "voices"


@needs_ffmpeg
def test_create_normalises_to_mono_48k():
    v = voices.create("Senandika", "Halo semua", wav_bytes(3.0), "rekaman.wav")
    assert v.duration == pytest.approx(3.0, abs=0.05)
    with wave.open(str(voices.ref_path(v.id))) as w:
        assert w.getnchannels() == 1 and w.getframerate() == 48000
    assert [x.id for x in voices.list_voices()] == [v.id]
    assert voices.get(v.id).transcript == "Halo semua"


@needs_ffmpeg
def test_create_rejects_too_long():
    with pytest.raises(ValueError, match="1–11,5"):
        voices.create("Panjang", "", wav_bytes(12.0), "x.wav")
    assert voices.list_voices() == []


@needs_ffmpeg
def test_delete_removes_folder():
    v = voices.create("A", "", wav_bytes(2.0), "a.wav")
    voices.delete(v.id)
    assert voices.get(v.id) is None and not voices.ref_path(v.id).parent.exists()
    with pytest.raises(LookupError):
        voices.delete(v.id)


def test_import_legacy(tmp_path):
    ref = tmp_path / "legacy_ref.wav"
    ref.write_bytes(wav_bytes(4.0, rate=48000))
    db = tmp_path / "studio.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE voices (id TEXT, nama TEXT, transkrip TEXT, path_wav TEXT, durasi REAL, created_at TEXT)")
    con.execute("INSERT INTO voices VALUES (?,?,?,?,?,?)", ("a" * 32, "Zephlyn", "Terkadang kita", str(ref), 4.0, "2026-09-25T16:12:59"))
    con.execute("INSERT INTO voices VALUES (?,?,?,?,?,?)", ("b" * 32, "Hilang", "", str(tmp_path / "missing.wav"), 3.0, "2026-09-25"))
    con.commit()
    con.close()

    assert voices.import_legacy(db) == 1
    v = voices.get("a" * 32)
    assert (v.name, v.transcript, v.duration) == ("Zephlyn", "Terkadang kita", 4.0)
    assert voices.ref_path(v.id).read_bytes() == ref.read_bytes()
    assert voices.import_legacy(db) == 0


def test_import_legacy_missing_db(tmp_path):
    with pytest.raises(FileNotFoundError):
        voices.import_legacy(tmp_path / "nope.db")


def test_ref_path_rejects_bad_id():
    with pytest.raises(ValueError):
        voices.ref_path("../x")
