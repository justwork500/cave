from fastapi.testclient import TestClient

from cave.api.app import create_app
from cave.settings import Settings


def test_health(tmp_path):
    app = create_app(Settings(db_path=tmp_path / "cave.db", config_dir=tmp_path))
    r = TestClient(app).get("/api/v1/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}
