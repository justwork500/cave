import asyncio
import dataclasses
import http.server
import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from cave.access.items import get_item, set_assignments, upsert_item
from cave.automation.effects import LiveEffects
from cave.automation.engine import Engine
from cave.runner.app import create_runner_app
from cave.scripts import service as service_mod
from cave.scripts.service import RunnerClient, RunnerError, ScriptService
from tests.conftest import lan_client, sign_in
from tests.engine_helpers import FakeEffects, automation

TOKEN = "r" * 40
SECRET_VALUE = "pve-token-9f8e7d"

ECHO = """\
# cave:
#   name: Echo
#   params:
#     who: { type: str, default: world }
#   secrets: [PROXMOX_TOKEN]
import json, os, sys
args = json.load(sys.stdin)
print("using token", os.environ["PROXMOX_TOKEN"])
print(json.dumps({"hello": args["who"], "token": os.environ["PROXMOX_TOKEN"]}))
"""

PLAIN = "# cave:\n#   name: Plain\nprint('{}')\n"
FAILS = "# cave:\n#   name: Fails\nprint('step 1')\nraise SystemExit(4)\n"


def runner_for(scripts_dir):
    client = TestClient(create_runner_app(scripts_dir, TOKEN))

    async def post(path, body, timeout):
        r = await asyncio.to_thread(client.post, path, json=body, headers={"Authorization": f"Bearer {TOKEN}"})
        if r.status_code != 200:
            raise RunnerError(f"The script runner said {r.status_code}.")
        return r.json()

    return post


def setup(app, monkeypatch, name="echo.py", text=ECHO):
    d = app.state.settings.config_dir / "scripts"
    d.mkdir(exist_ok=True)
    (d / name).write_text(text, encoding="utf-8")
    app.state.scripts.load_all()
    monkeypatch.setenv("CAVE_SECRET_PROXMOX_TOKEN", SECRET_VALUE)
    service: ScriptService = app.state.script_service
    service.runner = runner_for(d)
    return service


def test_run_records_log_and_audit(app, users, monkeypatch):
    service = setup(app, monkeypatch)
    result = asyncio.run(service.run("echo.py", {"who": "sam"}, "user:test"))
    assert result == {"hello": "sam", "token": "•••"}
    row = app.state.db.execute("SELECT * FROM script_runs").fetchone()
    assert row["outcome"] == "finished" and row["started_by"] == "user:test" and json.loads(row["params"]) == {
        "who": "sam"}
    entry = next(e for e in __import__("cave.audit", fromlist=["x"]).list_entries(app.state.db)
                 if e["action"] == "script.run")
    assert entry["target"] == "script:echo.py" and entry["new"]["outcome"] == "finished"


def test_bad_params_refused_before_runner(app, users, monkeypatch):
    service = setup(app, monkeypatch)
    called = []

    async def post(*a):
        called.append(a)
        return {}

    service.runner = post
    with pytest.raises(ValueError, match="unknown parameter"):
        asyncio.run(service.run("echo.py", {"whom": "x"}, "t"))
    assert called == []


def test_missing_secret_refused(app, users, monkeypatch):
    service = setup(app, monkeypatch)
    monkeypatch.delenv("CAVE_SECRET_PROXMOX_TOKEN")
    with pytest.raises(ValueError, match="PROXMOX_TOKEN isn't set"):
        asyncio.run(service.run("echo.py", {}, "t"))


def test_secret_never_leaves(app, users, monkeypatch):  # Review Focus 3
    setup(app, monkeypatch)
    admin = sign_in(lan_client(app), "admin", "pw-admin-1234", users.admin_totp)
    r = admin.post("/api/v1/scripts/echo.py/run", json={"params": {"who": "sam"}})
    assert r.status_code == 200 and SECRET_VALUE not in r.text
    runs = admin.get("/api/v1/scripts/echo.py/runs").text
    assert SECRET_VALUE not in runs and "•••" in runs
    dump = "\n".join(app.state.db._conn.iterdump())
    assert SECRET_VALUE not in dump
    fx = LiveEffects(app.state.states, app.state.db, app.state.bus, lambda: None, scripts=app.state.script_service)
    a = automation("    - type: script\n      ref: scripts/echo.py\n      result_var: out\n"
                   "    - type: notify\n      message: \"{{ out.token }}\"\n")
    trace = asyncio.run(Engine(app.state.states, fx, lambda _: None, lambda: __import__("datetime").datetime.now())
                        .run(a.actions, {}, source="automation:t"))
    assert trace.outcome == "finished" and SECRET_VALUE not in json.dumps(dataclasses.asdict(trace), default=str)


def test_runner_down_fails_fast(app, users, monkeypatch):  # Review Focus 5
    service = setup(app, monkeypatch)

    async def down(*a):
        raise RunnerError("The script runner can't be reached: connection refused")

    service.runner = down
    with pytest.raises(ValueError, match="can't be reached"):
        asyncio.run(service.run("echo.py", {}, "t"))
    fx = LiveEffects(app.state.states, app.state.db, app.state.bus, lambda: None, scripts=service)
    a = automation("    - type: script\n      ref: scripts/echo.py\n")
    trace = asyncio.run(Engine(app.state.states, fx, lambda _: None, lambda: __import__("datetime").datetime.now())
                        .run(a.actions, {}, source="t"))
    assert trace.outcome == "failed" and "can't be reached" in trace.error


def test_runner_client_timeout(monkeypatch):  # Review Focus 5
    class Silent(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            time.sleep(5)

        def log_message(self, *a):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Silent)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(service_mod, "RUNNER_SLACK", 0.5)
    try:
        client = RunnerClient(f"http://127.0.0.1:{server.server_port}", TOKEN)
        start = time.monotonic()
        with pytest.raises(RunnerError):
            asyncio.run(client.post("/run", {}, 0.5))
        assert time.monotonic() - start < 4
    finally:
        server.shutdown()
        server.server_close()


def test_no_runner_configured(app, users, monkeypatch):
    service = setup(app, monkeypatch)
    service.runner = None
    with pytest.raises(ValueError, match="isn't set up"):
        asyncio.run(service.run("echo.py", {}, "t"))


def test_run_api_access(app, users, monkeypatch):
    setup(app, monkeypatch, "plain.py", "# cave:\n#   name: Plain\nprint('{}')\n")
    sam = sign_in(lan_client(app), "sam", "pw-sam-1234")
    assert sam.post("/api/v1/scripts/plain.py/run", json={}).status_code == 403
    set_assignments(app.state.db, "test", "script:plain.py", [("user", users.sam.id)])
    r = sam.post("/api/v1/scripts/plain.py/run", json={})
    assert r.status_code == 200 and r.json() == {"result": {}}
    assert sam.get("/api/v1/scripts/plain.py/runs").status_code == 403


def script_row(client, file):
    return next(s for s in client.get("/api/v1/scripts").json() if s["file"] == file)


def change_item(app, file, **changes):
    item = get_item(app.state.db, f"script:{file}")
    upsert_item(app.state.db, "test", dataclasses.replace(item, **changes))


def disable(app, file):
    change_item(app, file, status="disabled")


def test_section_holder_runs_an_unrestricted_script(app, users, monkeypatch):
    setup(app, monkeypatch, "plain.py", PLAIN)
    op = sign_in(lan_client(app), "op", "pw-op-1234", users.op_totp)
    assert op.post("/api/v1/scripts/plain.py/run", json={}).status_code == 200
    assert script_row(op, "plain.py")["allowed"] is True


def test_assignment_restricts_running_for_section_holders(app, users, monkeypatch):
    setup(app, monkeypatch, "plain.py", PLAIN)
    set_assignments(app.state.db, "test", "script:plain.py", [("role", "household")])
    op = sign_in(lan_client(app), "op", "pw-op-1234", users.op_totp)
    assert op.post("/api/v1/scripts/plain.py/run", json={}).status_code == 403
    assert script_row(op, "plain.py")["allowed"] is False
    assert app.state.db.execute("SELECT count(*) FROM script_runs").fetchone()[0] == 0
    set_assignments(app.state.db, "test", "script:plain.py", [("role", "operator")])
    assert op.post("/api/v1/scripts/plain.py/run", json={}).status_code == 200


def test_disabled_script_is_refused_for_everyone(app, users, monkeypatch):
    setup(app, monkeypatch, "plain.py", PLAIN)
    set_assignments(app.state.db, "test", "script:plain.py", [("role", "operator")])
    disable(app, "plain.py")
    op = sign_in(lan_client(app), "op", "pw-op-1234", users.op_totp)
    admin = sign_in(lan_client(app), "admin", "pw-admin-1234", users.admin_totp)
    assert op.post("/api/v1/scripts/plain.py/run", json={}).status_code == 403
    assert admin.post("/api/v1/scripts/plain.py/run", json={}).status_code == 403
    assert script_row(op, "plain.py")["allowed"] is False


def test_disabled_without_assignments_is_refused(app, users, monkeypatch):
    setup(app, monkeypatch, "plain.py", PLAIN)
    disable(app, "plain.py")
    op = sign_in(lan_client(app), "op", "pw-op-1234", users.op_totp)
    assert op.post("/api/v1/scripts/plain.py/run", json={}).status_code == 403


def test_hidden_script_is_admin_only(app, users, monkeypatch):
    setup(app, monkeypatch, "plain.py", PLAIN)
    change_item(app, "plain.py", visibility="hide")
    op = sign_in(lan_client(app), "op", "pw-op-1234", users.op_totp)
    admin = sign_in(lan_client(app), "admin", "pw-admin-1234", users.admin_totp)
    assert op.post("/api/v1/scripts/plain.py/run", json={}).status_code == 403
    assert script_row(op, "plain.py")["allowed"] is False
    assert admin.post("/api/v1/scripts/plain.py/run", json={}).status_code == 200


def test_home_network_script_refuses_section_holders_outside(app, users, monkeypatch):
    setup(app, monkeypatch, "plain.py", PLAIN)
    change_item(app, "plain.py", network="local")
    away = sign_in(lan_client(app, "203.0.113.9"), "op", "pw-op-1234", users.op_totp)
    home = sign_in(lan_client(app), "op", "pw-op-1234", users.op_totp)
    assert away.post("/api/v1/scripts/plain.py/run", json={}).status_code == 403
    assert home.post("/api/v1/scripts/plain.py/run", json={}).status_code == 200


def test_automations_do_not_run_a_disabled_script(app, users, monkeypatch):
    service = setup(app, monkeypatch, "plain.py", PLAIN)
    disable(app, "plain.py")
    with pytest.raises(ValueError, match="turned off"):
        asyncio.run(service.run("plain.py", {}, "automation:a"))
    assert app.state.db.execute("SELECT count(*) FROM script_runs").fetchone()[0] == 0


def test_runs_kept_100(app, users, monkeypatch):
    service = setup(app, monkeypatch, "plain.py", "# cave:\n#   name: Plain\nprint('{}')\n")
    monkeypatch.setattr(service_mod, "KEEP_RUNS", 3)
    for _ in range(5):
        asyncio.run(service.run("plain.py", {}, "t"))
    assert app.state.db.execute("SELECT count(*) FROM script_runs").fetchone()[0] == 3


def test_script_failure_is_409_with_tail(app, users, monkeypatch):
    setup(app, monkeypatch, "fails.py", FAILS)
    admin = sign_in(lan_client(app), "admin", "pw-admin-1234", users.admin_totp)
    r = admin.post("/api/v1/scripts/fails.py/run", json={})
    assert r.status_code == 409 and "code 4" in r.json()["detail"] and "step 1" in r.json()["detail"]
    row = app.state.db.execute("SELECT outcome FROM script_runs").fetchone()
    assert row["outcome"] == "failed"


def test_engine_passes_source():
    fx = FakeEffects()
    a = automation("    - type: script\n      ref: scripts/x.py\n")
    asyncio.run(Engine(__import__("tests.engine_helpers", fromlist=["x"]).DictReader(), fx, lambda _: None,
                       lambda: __import__("datetime").datetime.now()).run(a.actions, {}, source="automation:z"))
    assert fx.calls == [("script", "scripts/x.py", None, {}, "automation:z")]
