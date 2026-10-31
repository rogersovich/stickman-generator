from fastapi.testclient import TestClient
from app.main import app
from app import config

client = TestClient(app)

def test_storage_status_endpoint():
    res = client.get("/api/storage/status")
    assert res.status_code == 200
    data = res.json()
    assert "d1_connected" in data
    assert "r2_connected" in data
    assert "total_projects" in data
    assert "backup_threshold" in data
    assert data["backup_threshold"] == 30
    assert "needs_backup" in data
    assert "rclone_backup_command" in data
    assert "rclone" in data["rclone_backup_command"]
