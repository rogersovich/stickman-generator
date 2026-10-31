import pytest
import audit

def test_audit_exact_match():
    res = audit.audit_transcription("Kamu pikir telat seminggu masih bisa diatur.", "Kamu pikir telat seminggu masih bisa diatur.")
    assert res["status"] == "ok"
    assert res["score"] == 1.0
    assert len(res["issues"]) == 0

def test_audit_missing_word():
    res = audit.audit_transcription("Tabunganmu masih cukup untuk bensin dan beras.", "Tabunganmu masih cukup untuk dan beras.")
    assert res["status"] == "warning"
    assert any("bensin" in issue for issue in res["issues"])

def test_audit_hallucination():
    res = audit.audit_transcription("Dia terdiam.", "Dia terdiam um uh mm yeah terdiam sekali.")
    assert res["status"] == "warning"
    assert any("tambahan" in issue for issue in res["issues"])

