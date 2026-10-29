from pathlib import Path

from cave.access.items import set_assignments
from cave.state import Entity
from tests.conftest import lan_client, sign_in
from tests.test_mqtt_bridge import FakePublisher

FIX = Path(__file__).parent / "fixtures" / "config"
TRIGGER = {"type": "state", "entity": "binary_sensor.ups_on_battery", "to": "on"}
SAMPLES = {"scripts/Stop-LabHosts.ps1": {"status": "3 hosts stopped"}}


def setup(app):
    for kind, name in (("automations", "ups-on-battery"), ("sequences", "lab_safe_shutdown")):
        folder = app.state.settings.config_dir / kind
        folder.mkdir(exist_ok=True)
        (folder / f"{name}.yaml").write_text((FIX / kind / f"{name}.yaml").read_text(encoding="utf-8"),
                                             encoding="utf-8")
    app.state.config.load_all()


def run_test(client, **body):
    payload = {"kind": "automation", "id": "ups-on-battery", "trigger": TRIGGER,
               "states": {"sensor.ups_battery_runtime_min": "12"}, "script_samples": SAMPLES} | body
    return client.post("/api/v1/test-center/run", json=payload)


def details(r):
    return [s["detail"] for s in r.json()["trace"]["steps"]]


def as_admin(app, users):
    return sign_in(lan_client(app), "admin", "pw-admin-1234", users.admin_totp)


def test_ups_example_whole_run(app, users):  # the spec's exit-gate item 3
    setup(app)
    r = run_test(as_admin(app, users))
    assert r.status_code == 200, r.text
    d = details(r)
    assert "What if: notify: UPS on battery. 12 min left." in d
    assert "What if: turn_off switch.proxmox_vm_media" in d
    assert any(x.startswith("What if: script scripts/Stop-LabHosts.ps1") and "not run" in x for x in d)
    assert "What if: notify: Lab shutdown: 3 hosts stopped." in d
    assert any(x.startswith("What if: binary_sensor.ups_on_battery") for x in d)
    assert d[-1] == "Done. 0 devices changed, 0 messages sent, 0 scripts run."
    assert r.json()["summary"] == {"devices_changed": 0, "messages_sent": 0, "scripts_run": 0}
    assert r.json()["trace"]["outcome"] == "finished"


def test_ups_example_step_two_only(app, users):
    setup(app)
    r = run_test(as_admin(app, users), start_at="actions[1]")
    d = details(r)
    assert d[0] == "skipped (before the start point)"
    assert "What if: turn_off switch.proxmox_vm_media" in d
    assert not any("UPS on battery" in x for x in d)


def test_conditions_fail_reported(app, users):
    setup(app)
    r = run_test(as_admin(app, users), states={"sensor.ups_battery_runtime_min": "30"})
    assert r.json()["trace"]["outcome"] == "conditions_not_met"


def test_zero_side_effects(app, users):  # Review Focus 4
    setup(app)
    states, db = app.state.states, app.state.db
    states.register(Entity("switch.proxmox_vm_media", "VM", None, "switch"))
    states.register(Entity("binary_sensor.ups_on_battery", "UPS", None, "binary_sensor"))
    states.set("switch.proxmox_vm_media", "on")
    states.set("binary_sensor.ups_on_battery", "off")
    commands = []

    async def handler(entity_id, command, args):
        commands.append((entity_id, command))

    states.set_command_handler("switch", handler)
    publisher = FakePublisher()
    app.state.mqtt = type("M", (), {"bridge": type("B", (), {"publish": publisher})()})()
    queue = app.state.bus.subscribe()
    before = {e.entity_id: states.get(e.entity_id).value for e in states.entities()}
    notes = db.execute("SELECT count(*) FROM notifications").fetchone()[0]

    r = run_test(as_admin(app, users))
    assert r.status_code == 200
    assert {e.entity_id: states.get(e.entity_id).value for e in states.entities()} == before
    assert commands == [] and publisher.calls == []
    assert db.execute("SELECT count(*) FROM notifications").fetchone()[0] == notes
    assert queue.empty()  # nothing on the bus: no state changes, no notifications, nothing for other automations


def test_draft_not_written(app, users):
    setup(app)
    draft = (FIX / "automations" / "ups-on-battery.yaml").read_text().replace("id: ups-on-battery", "id: draft-ups")
    r = run_test(as_admin(app, users), id="draft-ups", yaml=draft)
    assert r.status_code == 200 and r.json()["trace"]["outcome"] == "finished"
    assert not (app.state.settings.config_dir / "automations" / "draft-ups.yaml").exists()
    bad = run_test(as_admin(app, users), id="draft-ups", yaml=draft.replace("on_timeout:", "on_timout:"))
    assert bad.status_code == 422 and ":" in bad.json()["detail"]


def test_feature_and_reference_guard(app, users):
    setup(app)
    sam = sign_in(lan_client(app), "sam", "pw-sam-1234")
    assert run_test(sam).status_code == 403  # no Test Center feature
    op = sign_in(lan_client(app), "op", "pw-op-1234", users.op_totp)
    r = run_test(op)  # operators have the Test Center, but not these devices
    assert r.status_code == 403 and "binary_sensor.ups_on_battery" in r.json()["detail"]
    set_assignments(app.state.db, "test", "sequence:lab_safe_shutdown", [("role", "operator")])


def test_test_traces_stored_separately(app, users):
    setup(app)
    run_test(as_admin(app, users))
    rows = app.state.db.execute("SELECT item_id, test FROM automation_traces").fetchall()
    assert [(r["item_id"], r["test"]) for r in rows] == [("automation:ups-on-battery", 1)]


def test_sequence_what_if(app, users):
    setup(app)
    r = as_admin(app, users).post("/api/v1/test-center/run", json={
        "kind": "sequence", "id": "lab_safe_shutdown", "variables": {"grace_seconds": 5},
        "script_samples": SAMPLES})
    assert r.status_code == 200 and "What if: notify: Lab shutdown: 3 hosts stopped." in details(r)
