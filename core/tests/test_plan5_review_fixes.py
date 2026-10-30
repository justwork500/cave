"""Tests for the Plan 5 whole-branch review findings."""

import asyncio
import sys
import threading
import time

import pytest
from fastapi.testclient import TestClient

from cave.access.items import set_assignments
from cave.runner import execute as execute_mod
from cave.runner.__main__ import main
from cave.runner.app import create_runner_app
from cave.runner.execute import MASK, execute, mask_value, masker
from cave.scripts.service import ScriptService
from tests.conftest import lan_client, sign_in

linux_only = pytest.mark.skipif(sys.platform != "linux", reason="process sessions, uids and /proc are Linux-only")
TOKEN = "t" * 40


def write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8", newline="\n")
    return p


# ---- 1 (Critical): nothing outlives a run; secret runs are exclusive; scripts get their own uid ----

def test_sweep_kills_only_the_script_uid(tmp_path):
    """A child that escapes into its own session is caught by the sweep: every process of the script uid dies."""
    for pid, uid in (("100", 10002), ("200", 0), ("300", 10002), ("self", 10002)):
        (tmp_path / pid).mkdir()
        (tmp_path / pid / "status").write_text(f"Name:\tx\nUid:\t{uid}\t{uid}\t{uid}\t{uid}\n", encoding="utf-8")
    (tmp_path / "not-a-pid").mkdir()
    killed = []
    execute_mod.sweep(10002, proc=tmp_path, kill=lambda pid: killed.append(pid))
    assert sorted(killed) == [100, 300]


def test_children_of_the_process_group_are_killed_after_exit(tmp_path):
    marker = tmp_path / "marker"
    script = ("import subprocess, sys, json, time\n"
              f"subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(2); open(\"{marker.as_posix()}\", \"w\")'])\n"
              "time.sleep(0.5)\n"
              "print(json.dumps({}))\n")
    if sys.platform == "win32":
        pytest.skip("Windows loses the process tree once the parent exits; the runner targets Linux")
    r = asyncio.run(execute(write(tmp_path, "a.py", script), "python", {}, {}, 10))
    assert r.error is None
    time.sleep(3)
    assert not marker.exists()


@linux_only
def test_scripts_run_as_the_script_uid(tmp_path, monkeypatch):
    seen = {}
    real = asyncio.create_subprocess_exec

    async def spy(*args, **kwargs):
        seen.update(kwargs)
        kwargs.pop("user", None)
        kwargs.pop("group", None)
        return await real(*args, **kwargs)

    monkeypatch.setattr(execute_mod.asyncio, "create_subprocess_exec", spy)
    asyncio.run(execute(write(tmp_path, "a.py", "print('{}')\n"), "python", {}, {}, 10, run_as=(10002, 10002)))
    assert seen["user"] == 10002 and seen["group"] == 10002


def test_secret_runs_never_overlap(tmp_path):
    slow = write(tmp_path, "slow.py", "import time, json\ntime.sleep(1.5)\nprint(json.dumps({'t': time.time()}))\n")
    quick = write(tmp_path, "quick.py", "import time, json\nprint(json.dumps({'t': time.time()}))\n")
    gate = execute_mod.RunGate()

    async def go():
        first = asyncio.create_task(gate.run(execute(slow, "python", {}, {}, 10), exclusive=False))
        await asyncio.sleep(0.3)
        second = asyncio.create_task(gate.run(execute(quick, "python", {}, {"TOKEN": "abcd1234"}, 10),
                                              exclusive=True))
        a, b = await asyncio.gather(first, second)
        return a.result["t"], b.result["t"]

    slow_done, secret_ran = asyncio.run(go())
    assert secret_ran > slow_done  # the secret run waited for the other run to finish


def test_token_comes_from_a_file(tmp_path, monkeypatch):
    f = tmp_path / "token"
    f.write_text("x" * 40 + "\n", encoding="utf-8")
    calls = {}
    monkeypatch.setattr("cave.runner.__main__.uvicorn.run", lambda app, **kw: calls.update(kw))
    monkeypatch.delenv("CAVE_RUNNER_TOKEN", raising=False)
    main(["--scripts", str(tmp_path), "--token-file", str(f)])
    assert calls["port"] == 8099


# ---- 2 (Important): secrets in dict keys ----

def test_mask_dict_keys():
    mask = masker({"T": "supersecretvalue"})
    assert mask_value({"supersecretvalue": {"x": "supersecretvalue"}}, mask) == {MASK: {"x": MASK}}


def test_secret_as_result_key_masked(tmp_path):
    script = "import os, json\nprint(json.dumps({os.environ['TOK']: 1}))\n"
    r = asyncio.run(execute(write(tmp_path, "a.py", script), "python", {}, {"TOK": "supersecretvalue"}, 10))
    assert r.result == {MASK: 1}


# ---- 3 (Important): cancelling stops the script ----

def test_execute_kills_tree_on_cancel(tmp_path):
    marker = tmp_path / "marker"
    script = ("import subprocess, sys, time\n"
              f"subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(2); open(\"{marker.as_posix()}\", \"w\")'])\n"
              "time.sleep(30)\n")

    async def go():
        task = asyncio.create_task(execute(write(tmp_path, "a.py", script), "python", {}, {}, 60))
        await asyncio.sleep(0.8)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    start = time.monotonic()
    asyncio.run(go())
    assert time.monotonic() - start < 5
    time.sleep(2.5)
    assert not marker.exists()


def test_runner_cancel_endpoint(tmp_path):
    d = tmp_path / "scripts"
    d.mkdir()
    (d / "slow.py").write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    auth = {"Authorization": f"Bearer {TOKEN}"}
    out = {}
    with TestClient(create_runner_app(d, TOKEN)) as client:  # one event loop for both requests, as in production

        def run():
            out["r"] = client.post("/run", json={"script": "slow.py", "params": {}, "secrets": {}, "timeout": 60,
                                                 "run_id": "r1"}, headers=auth)

        t = threading.Thread(target=run)
        start = time.monotonic()
        t.start()
        time.sleep(1)
        assert client.post("/cancel/r1", headers=auth).status_code == 204
        t.join(10)
    assert time.monotonic() - start < 8 and "cancelled" in out["r"].json()["error"]


def test_service_cancels_the_runner_run(app, users, monkeypatch):
    d = app.state.settings.config_dir / "scripts"
    d.mkdir()
    (d / "slow.py").write_text("# cave:\n#   name: Slow\nimport time\ntime.sleep(30)\n", encoding="utf-8")
    app.state.scripts.load_all()
    service: ScriptService = app.state.script_service
    posts = []

    async def runner(path, body, timeout):
        posts.append((path, body))
        if path == "/run":
            await asyncio.sleep(60)
        return {}

    service.runner = runner

    async def go():
        task = asyncio.create_task(service.run("slow.py", {}, "t"))
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0.1)

    asyncio.run(go())
    run_id = posts[0][1]["run_id"]
    assert ("/cancel/" + run_id, {}) in posts


# ---- 4 (Important) + 11: an Admin's restriction on a script holds for editing and reading ----

def test_edit_needs_item_access_once_restricted(app, users):
    admin = sign_in(lan_client(app), "admin", "pw-admin-1234", users.admin_totp)
    plain = "# cave:\n#   name: X\nprint('{}')\n"
    admin.put("/api/v1/scripts/x.py", json={"text": plain})
    op = sign_in(lan_client(app), "op", "pw-op-1234", users.op_totp)
    assert op.put("/api/v1/scripts/x.py", json={"text": plain}).status_code == 200  # not restricted yet
    set_assignments(app.state.db, "test", "script:x.py", [("role", "household")])  # an Admin restricts it
    assert op.put("/api/v1/scripts/x.py", json={"text": plain}).status_code == 403
    assert op.delete("/api/v1/scripts/x.py").status_code == 403
    assert op.get("/api/v1/scripts/x.py").status_code == 403
    assert op.get("/api/v1/scripts/x.py/runs").status_code == 403


# ---- 5 (Important): reload reloads scripts ----

def test_reload_reloads_scripts(app, users):
    d = app.state.settings.config_dir / "scripts"
    d.mkdir()
    (d / "x.py").write_text("# cave:\n#   name: Old\nprint('{}')\n", encoding="utf-8")
    app.state.scripts.load_all()
    (d / "x.py").write_text("# cave:\n#   name: New\nprint('{}')\n", encoding="utf-8")
    admin = sign_in(lan_client(app), "admin", "pw-admin-1234", users.admin_totp)
    assert admin.post("/api/v1/config/reload").status_code == 204
    assert app.state.scripts.get("x.py").header.name == "New"


