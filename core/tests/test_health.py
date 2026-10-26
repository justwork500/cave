from fastapi.testclient import TestClient


def test_health(app):
    r = TestClient(app).get("/api/v1/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}
