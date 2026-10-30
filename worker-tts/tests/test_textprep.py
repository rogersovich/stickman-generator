import re

from textprep import normalize_numbers, prepare, split_sentences


def test_normalize_numbers_id_and_en():
    assert normalize_numbers("Gaji 3 bulan", "id") == "Gaji tiga bulan"
    assert normalize_numbers("Gaji 3 bulan", "en") == "Gaji three bulan"


def test_normalize_keeps_text_without_numbers():
    assert normalize_numbers("Kalau hujan turun,", "id") == "Kalau hujan turun,"


def test_split_keeps_short_text_whole():
    text = "Kamu guru honorer di sebuah sekolah dasar di pinggir kota."
    assert split_sentences(text) == [text]


def test_split_long_text():
    s1 = "Setiap pagi kamu berangkat sebelum matahari tinggi, melewati jalan tanah yang becek."
    s2 = "Di kelas, anak-anak sudah menunggu dengan buku tulis yang sampulnya sudah lusuh dan robek di ujungnya."
    s3 = ("Kamu mengajar dengan sabar walaupun gajimu sudah telat tiga bulan, karena kamu tahu mereka butuh guru "
          "yang datang setiap hari tanpa alasan apa pun dan tanpa mengeluh sedikit pun.")
    text = f"{s1} {s2} {s3}"
    pieces = split_sentences(text, max_chars=200)
    assert len(pieces) >= 2 and all(0 < len(p) <= 200 for p in pieces)
    assert re.sub(r"\s+", " ", " ".join(pieces)) == text


def test_split_overlong_sentence_without_punctuation():
    text = " ".join(["kata"] * 120)
    pieces = split_sentences(text, max_chars=200)
    assert all(0 < len(p) <= 200 for p in pieces) and " ".join(pieces) == text


def test_prepare_voxcpm_adds_period():
    assert prepare("Kalau hujan turun", "id", "voxcpm2") == ["Kalau hujan turun."]
    assert prepare("Kalau hujan turun", "id", "omnivoice") == ["Kalau hujan turun"]
    assert prepare("Lalu...", "id", "voxcpm2") == ["Lalu..."]
