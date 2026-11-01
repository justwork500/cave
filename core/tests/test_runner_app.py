import os

import pytest
from fastapi.testclient import TestClient

from cave.runner.__main__ import main
from cave.runner.app import create_runner_app

TOKEN = "t" * 40
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def scripts(tmp_path):
    d = tmp_path / "scripts"
    d.mkdir()
    (d / "hello.py").write_text("import json, sys\nprint(json.dumps({'hi': json.load(sys.stdin)['who']}))\n")
    return d


@pytest.fixture
def client(scripts):
    return TestClient(create_runner_app(scripts, TOKEN))


def body(script="hello.py", **kw):
    return {"script": script, "params": {"who": "sam"}, "secrets": {}, "timeout": 10} | kw


def test_runs_script_and_returns_result(client):
    r = client.post("/run", json=body(), headers=AUTH)
    assert r.status_code == 200 and r.json()["result"] == {"hi": "sam"} and r.json()["error"] is None


def test_script_failure_is_still_200(client, scripts):
    (scripts / "bad.py").write_text("raise SystemExit(2)\n")
    r = client.post("/run", json=body("bad.py", params={}), headers=AUTH)
    assert r.status_code == 200 and r.json()["exit_code"] == 2


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}, {"Authorization": TOKEN}])
def test_token_required(client, headers):
    assert client.post("/run", json=body(), headers=headers).status_code == 401
    assert client.get("/health", headers=headers).status_code == 401


@pytest.mark.parametrize("name", ["../x.py", "/etc/passwd", "sub/x.py", "x\\y.py", "..", "hello.exe", "a..b.py"])
def test_path_tricks_refused(client, name):  # Review Focus 1
    assert client.post("/run", json=body(name), headers=AUTH).status_code == 400


def test_symlink_outside_refused(client, scripts, tmp_path):  # Review Focus 1
    outside = tmp_path / "outside.py"
    outside.write_text("print('{}')\n")
    try:
        os.symlink(outside, scripts / "link.py")
    except (OSError, NotImplementedError):
        pytest.skip("can't create symlinks here")
    assert client.post("/run", json=body("link.py"), headers=AUTH).status_code == 400


def test_unknown_script_404(client):
    assert client.post("/run", json=body("nope.py"), headers=AUTH).status_code == 404


@pytest.mark.parametrize("timeout", [3601, 0, -1])
def test_bad_timeout_422(client, timeout):
    assert client.post("/run", json=body(timeout=timeout), headers=AUTH).status_code == 422


def test_health_lists_interpreters(client):
    r = client.get("/health", headers=AUTH).json()
    assert r["status"] == "ok" and r["interpreters"]["python3"] is True and set(r["interpreters"]) == {
        "pwsh", "python3", "bash"}


def test_main_refuses_short_token(monkeypatch):
    monkeypatch.setenv("CAVE_RUNNER_TOKEN", "short")
    with pytest.raises(SystemExit):
        main(["--scripts", "."])
    monkeypatch.delenv("CAVE_RUNNER_TOKEN")
    with pytest.raises(SystemExit):
        main(["--scripts", "."])


def test_runner_uses_the_asyncio_loop(tmp_path, monkeypatch):
    """uvicorn[standard] would pick uvloop, whose subprocess call refuses user= and group=: every script run
    failed in the real container. Found on the first Debian 13 install."""
    from cave.runner import __main__ as runner_main

    seen = {}
    monkeypatch.setattr(runner_main.uvicorn, "run", lambda app, **kw: seen.update(kw))
    token = tmp_path / "token"
    token.write_text("t" * 40, encoding="utf-8")
    runner_main.main(["--scripts", str(tmp_path), "--token-file", str(token)])
    assert seen["loop"] == "asyncio"
