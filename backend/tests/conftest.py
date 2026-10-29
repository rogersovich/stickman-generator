import pytest

from app import settings


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Never read or write the real backend/settings.json in tests."""
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
