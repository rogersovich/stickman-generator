import pytest

from app import config, settings


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Never read or write the real backend/settings.json or real cloud DB in tests."""
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(config, "CLOUDFLARE_D1_DATABASE_ID", "")
    monkeypatch.setattr(config, "R2_BUCKET_NAME", "")
