import pytest

from cave.api import console
from tests.conftest import lan_client


@pytest.fixture
def built(tmp_path, monkeypatch):
    d = tmp_path / "console"
    (d / "assets").mkdir(parents=True)
    (d / "index.html").write_text("<!doctype html><title>CAVE</title><div id=root></div>", encoding="utf-8")
    (d / "assets" / "app-1a2b3c.js").write_text("console.log('hi')", encoding="utf-8")
    monkeypatch.setattr(console, "CONSOLE_DIR", d)
    return d


@pytest.mark.parametrize("path", ["/", "/d/kids", "/admin/users", "/login", "/setup"])
def test_spa_fallback_for_client_routes(app, built, path):
    r = lan_client(app).get(path)
    assert r.status_code == 200 and "<div id=root>" in r.text and r.headers["cache-control"] == "no-store"


def test_api_routes_not_shadowed(app, built):
    c = lan_client(app)
    assert c.get("/api/v1/health").json() == {"status": "ok"}
    r = c.get("/api/v1/nope/at/all")
    assert r.status_code in (401, 404) and r.headers["content-type"].startswith("application/json")
    assert c.get("/spike").status_code == 200 and "spike.js" in c.get("/spike").text


def test_assets_cached_index_not(app, built):
    r = lan_client(app).get("/assets/app-1a2b3c.js")
    assert r.status_code == 200 and "immutable" in r.headers["cache-control"]
    assert lan_client(app).get("/assets/missing.js").status_code == 404


def test_security_headers(app, built):
    r = lan_client(app).get("/")
    csp = r.headers["content-security-policy"]
    assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp and "script-src 'self'" in csp
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["referrer-policy"] == "no-referrer"


def test_missing_build_message(app, tmp_path, monkeypatch):
    monkeypatch.setattr(console, "CONSOLE_DIR", tmp_path / "nothing")
    r = lan_client(app).get("/")
    assert r.status_code == 200 and "pnpm --dir console build" in r.text


@pytest.mark.parametrize("path", ["/assets/..%2F..%2Fdb.py", "/assets/%2e%2e/%2e%2e/db.py", "/assets/..%5Cx"])
def test_no_path_escape(app, built, path):
    assert lan_client(app).get(path).status_code == 404


@pytest.mark.parametrize("path", ["/enroll", "/spike"])
def test_server_pages_work_under_the_csp(app, built, path):
    """script-src 'self' blocks inline scripts, so every page CAVE serves must load its script from a file."""
    import re

    r = lan_client(app).get(path)
    assert "script-src 'self'" in r.headers["content-security-policy"]
    scripts = re.findall(r"<script\b([^>]*)>(.*?)</script>", r.text, re.DOTALL)
    assert scripts and all('src="/static/' in attrs and not body.strip() for attrs, body in scripts)


def test_csp_allows_websockets_only_to_this_origin(app, built):
    csp = lan_client(app).get("/").headers["content-security-policy"]
    assert "connect-src 'self';" in csp and "wss:" not in csp
