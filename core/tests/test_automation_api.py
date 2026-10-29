import time
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from cave.access.items import set_assignments
from cave.state import Entity
from tests.conftest import sign_in
from tests.test_config_api import GARAGE_AUTOMATION, KIDS_AUTOMATION, put_file

SLOW = """\
automation:
  id: slow
  name: Slow
  triggers:
    - type: time
      at: "03:00"
  actions:
    - type: delay
      duration: 60
"""


@pytest.fixture
def live(app, users) -> Iterator[TestClient]:
    """The app with its lifespan running, so the automation manager is up."""
    put_file(app, "automation", "kids-off", KIDS_AUTOMATION)
    put_file(app, "automation", "close-garage", GARAGE_AUTOMATION)
    put_file(app, "automation", "slow", SLOW)
    app.state.config.load_all()
    app.state.states.register(Entity("light.kids_room", "Kids", None, "light"))
    calls = []

    async def handler(entity_id, command, args):
        calls.append((entity_id, command))

    app.state.states.set_command_handler("light", handler)
    app.state.test_calls = calls
    with TestClient(app, base_url="https://testserver", client=("192.168.1.5", 50000)) as c:
        yield c


def wait_for_trace(c, kind, ident, outcome="finished"):
    for _ in range(100):
        traces = c.get(f"/api/v1/{kind}/{ident}/traces").json()
        if traces and traces[0]["outcome"] == outcome:
            return traces[0]
        time.sleep(0.02)
    raise AssertionError(f"no {outcome} trace: {traces}")


def test_household_runs_assigned_action(app, users, live):
    set_assignments(app.state.db, "test", "automation:kids-off", [("role", "household")])
    sign_in(live, "sam", "pw-sam-1234")
    r = live.post("/api/v1/automations/kids-off/run", json={})
    assert r.status_code == 200 and isinstance(r.json()["trace_id"], int)
    admin = TestClient(app, base_url="https://testserver", client=("192.168.1.5", 50001))
    sign_in(admin, "admin", "pw-admin-1234", users.admin_totp)
    wait_for_trace(admin, "automations", "kids-off")
    assert app.state.test_calls == [("light.kids_room", "turn_off")]


def test_run_refused_without_assignment(live, users):
    sign_in(live, "sam", "pw-sam-1234")
    assert live.post("/api/v1/automations/kids-off/run", json={}).status_code == 403
    assert live.post("/api/v1/automations/nope/run", json={}).status_code == 404


def test_single_mode_409(live, users):
    sign_in(live, "admin", "pw-admin-1234", users.admin_totp)
    assert live.post("/api/v1/automations/slow/run", json={}).status_code == 200
    r = live.post("/api/v1/automations/slow/run", json={})
    assert r.status_code == 409 and r.json() == {"detail": "It's already running."}


def test_traces_permission_and_redaction(app, users, live):
    sign_in(live, "admin", "pw-admin-1234", users.admin_totp)
    live.post("/api/v1/automations/close-garage/run", json={})
    wait_for_trace(live, "automations", "close-garage", outcome="failed")  # no handler for the cover: fails
    aud = TestClient(app, base_url="https://testserver", client=("192.168.1.5", 50002))
    sign_in(aud, "aud", "pw-aud-1234")
    assert aud.get("/api/v1/automations/close-garage/traces").status_code == 403  # not assigned the automation
    set_assignments(app.state.db, "test", "automation:close-garage", [("role", "auditor")])
    [t] = aud.get("/api/v1/automations/close-garage/traces").json()
    assert all(s["detail"] == "restricted" and s["data"] == {} for s in t["trace"]["steps"])
    assert "cover.garage_door" not in str(t)
    sam = TestClient(app, base_url="https://testserver", client=("192.168.1.5", 50003))
    sign_in(sam, "sam", "pw-sam-1234")
    assert sam.get("/api/v1/automations/close-garage/traces").status_code == 403
