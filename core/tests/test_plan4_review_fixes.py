"""Tests for the Plan 4 whole-branch review findings."""

import asyncio
import inspect
from datetime import datetime

import pytest

from cave.access.items import set_assignments
from cave.automation import engine as engine_mod
from cave.automation.effects import Trace
from cave.automation.manager import finish_trace, list_traces, new_trace
from cave.config.yamlfile import ConfigError, load_text
from tests.conftest import lan_client, sign_in
from tests.engine_helpers import DictReader, FakeEffects, automation, run
from tests.test_config_api import KIDS_AUTOMATION, put_file
from tests.test_manager import auto, make, settle, write

PEEK = """\
sequence:
  id: peek
  name: Peek
  actions:
    - type: notify
      message: "secret is {{ states('sensor.secret') }}"
"""

PARAM = """\
sequence:
  id: param
  name: Param
  fields:
    which: { type: str, default: sensor.secret }
  actions:
    - type: notify
      message: "{{ states(which) }}"
"""

DRAFT = """\
automation:
  id: draft-peek
  name: Draft
  triggers:
    - type: startup
  actions:
    - type: sequence
      ref: sequence.peek
"""


def as_op(app, users):
    return sign_in(lan_client(app), "op", "pw-op-1234", users.op_totp)


# ---- 1 (Critical): a broken template must not stop CAVE ----

def test_broken_template_is_a_load_error_not_a_crash(app, users):
    bad = KIDS_AUTOMATION + '    - type: notify\n      message: "{{ oops "\n'
    put_file(app, "automation", "kids-off", bad)
    app.state.config.load_all()  # must not raise
    assert app.state.config.errors["automations/kids-off.yaml"].startswith("kids-off.yaml:13: ")


def test_disallowed_template_refused_at_save(app, users):
    text = KIDS_AUTOMATION + "    - type: notify\n      message: \"{% set f = states %}{{ f('x.y') }}\"\n"
    admin = sign_in(lan_client(app), "admin", "pw-admin-1234", users.admin_totp)
    r = admin.put("/api/v1/automations/kids-off", json={"yaml": text})
    assert r.status_code == 422 and "kids-off.yaml:13" in r.json()["detail"]


# ---- 2 (Critical): deeply nested YAML ----

def test_deep_yaml_is_a_config_error():
    with pytest.raises(ConfigError, match="nested"):
        load_text("a: " + "[" * 50000 + "]" * 50000, "deep.yaml")


def test_deep_yaml_file_does_not_stop_load(app, users):
    put_file(app, "automation", "deep", "a: " + "[" * 5000 + "]" * 5000)
    app.state.config.load_all()
    assert "automations/deep.yaml" in app.state.config.errors


# ---- 3 (Critical) + 9: reads through routines ----

def test_test_center_checks_called_routines(app, users):
    put_file(app, "sequence", "peek", PEEK)
    app.state.config.load_all()
    set_assignments(app.state.db, "test", "sequence:peek", [("role", "operator")])
    r = as_op(app, users).post("/api/v1/test-center/run", json={
        "kind": "automation", "id": "draft-peek", "yaml": DRAFT})
    assert r.status_code == 403 and "sensor.secret" in r.json()["detail"]


def test_parameterized_routine_refused_in_test_center(app, users):
    put_file(app, "sequence", "param", PARAM)
    app.state.config.load_all()
    set_assignments(app.state.db, "test", "sequence:param", [("role", "operator")])
    r = as_op(app, users).post("/api/v1/test-center/run", json={
        "kind": "sequence", "id": "param", "variables": {"which": "sensor.secret"}})
    assert r.status_code == 403


def test_test_center_needs_the_item(app, users):
    put_file(app, "automation", "kids-off", KIDS_AUTOMATION)
    app.state.config.load_all()
    r = as_op(app, users).post("/api/v1/test-center/run", json={"kind": "automation", "id": "kids-off"})
    assert r.status_code == 403  # the automation isn't assigned to operators


def test_traces_need_the_item_and_redact_routines(app, users):
    put_file(app, "sequence", "peek", PEEK)
    app.state.config.load_all()
    iid = "sequence:peek"
    tid = new_trace(app.state.db, iid)
    finish_trace(app.state.db, iid, tid, Trace())
    c = as_op(app, users)
    assert c.get("/api/v1/sequences/peek/traces").status_code == 403
    set_assignments(app.state.db, "test", iid, [("role", "operator")])
    t = c.get("/api/v1/sequences/peek/traces").json()
    assert t and t[0]["trace"]["variables"] == {}  # redacted: it reads sensor.secret


def test_variables_into_dynamic_routine_refused(app, users):
    put_file(app, "sequence", "param", PARAM)
    app.state.config.load_all()
    set_assignments(app.state.db, "test", "sequence:param", [("role", "household")])
    sam = sign_in(lan_client(app), "sam", "pw-sam-1234")
    r = sam.post("/api/v1/sequences/param/run", json={"variables": {"which": "lock.front"}})
    assert r.status_code == 403


# ---- 4 (Important): a total step budget ----

def test_step_budget(monkeypatch):
    monkeypatch.setattr(engine_mod, "MAX_STEPS", 50)
    a = automation("""\
    - type: repeat
      count: 1000
      actions:
        - type: set_variable
          name: x
          value: 1
""")
    e = engine_mod.Engine(DictReader(), FakeEffects(), lambda _: None, lambda: datetime(2026, 1, 1))
    t = run(e.run(a.actions, {}, source="t"))
    assert t.outcome == "failed" and "steps" in t.error and len(t.steps) <= 60


def test_long_run_yields_to_the_loop():
    a = automation("""\
    - type: repeat
      count: 900
      actions:
        - type: set_variable
          name: x
          value: 1
""")
    async def go():
        ticks = 0

        async def ticker():
            nonlocal ticks
            while True:
                ticks += 1
                await asyncio.sleep(0)

        t = asyncio.create_task(ticker())
        await engine_mod.Engine(DictReader(), FakeEffects(), lambda _: None, lambda: datetime(2026, 1, 1)).run(
            a.actions, {}, source="t")
        t.cancel()
        return ticks

    assert asyncio.run(go()) > 1


# ---- 5 (Important): trimming must not delete runs still going ----

def test_trim_keeps_unfinished_runs(db):
    ids = [new_trace(db, "automation:x") for _ in range(25)]
    finish_trace(db, "automation:x", ids[-1], Trace())
    finish_trace(db, "automation:x", ids[0], Trace())  # must not raise
    assert len(list_traces(db, "automation:x")) == 2


def test_finish_missing_row_tolerated(db):
    finish_trace(db, "automation:x", 9999, Trace())


# ---- 6 (Important): routine runs are capped ----

def test_sequence_runs_capped(db, tmp_path):
    folder = tmp_path / "sequences"
    folder.mkdir()
    (folder / "slow.yaml").write_text(
        "sequence:\n  id: slow\n  name: Slow\n  actions:\n    - type: delay\n      duration: 60\n", encoding="utf-8")

    async def go():
        from tests.test_manager import GatedEffects

        fx = GatedEffects()
        m, *_ = await make(db, tmp_path, fx)
        results = [m.run_sequence("slow", {}) for _ in range(12)]
        await settle()
        await m.stop()
        return results

    results = asyncio.run(go())
    assert results.count(None) == 2 and all(isinstance(r, int) for r in results[:10])


# ---- 7 (Important): rearm keeps timers of untouched automations ----

def test_rearm_keeps_pending_for_timers(db, tmp_path):
    write(tmp_path, "held", auto("held", 'type: state\n      entity: binary_sensor.door\n      to: "on"\n      for: 120'))

    async def go():
        m, states, fx, _clock, sleeper = await make(db, tmp_path)
        states.set("binary_sensor.door", "on")
        await settle()
        m.rearm()  # someone saved an unrelated dashboard
        sleeper.release()
        await settle()
        await m.stop()
        return [c for c in fx.calls if c[0] == "call"]

    assert len(asyncio.run(go())) == 1


# ---- 8 (Important): config writes rearm on the event loop ----

def test_config_routes_are_async():
    from cave.api import config as config_api

    for fn in (config_api.put_doc, config_api.delete_doc, config_api.reload):
        assert inspect.iscoroutinefunction(fn), fn.__name__

