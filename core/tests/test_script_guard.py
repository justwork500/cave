from pathlib import Path

from cave.access.items import set_assignments
from tests.conftest import lan_client, sign_in

FIX = Path(__file__).parent / "fixtures" / "config"

CALLS_SCRIPT = """\
automation:
  id: report
  name: Report
  triggers:
    - type: startup
  actions:
    - type: script
      ref: scripts/disk.sh
"""

CALLS_ROUTINE = """\
automation:
  id: via-routine
  name: Via routine
  triggers:
    - type: startup
  actions:
    - type: sequence
      ref: sequence.lab_safe_shutdown
"""


def put(app, folder, name, text):
    d = app.state.settings.config_dir / folder
    d.mkdir(exist_ok=True)
    (d / name).write_text(text, encoding="utf-8")


def load_ups(app):
    for folder, name in (("automations", "ups-on-battery.yaml"), ("sequences", "lab_safe_shutdown.yaml"),
                         ("scripts", "Stop-LabHosts.ps1")):
        put(app, folder, name, (FIX / folder / name).read_text(encoding="utf-8"))
    app.state.scripts.load_all()
    app.state.config.load_all()


def as_op(app, users):
    return sign_in(lan_client(app), "op", "pw-op-1234", users.op_totp)


def as_admin(app, users):
    return sign_in(lan_client(app), "admin", "pw-admin-1234", users.admin_totp)


def test_operator_needs_script_item_to_save_automation(app, users):
    put(app, "scripts", "disk.sh", "# cave:\n#   name: Disk\necho '{}'\n")
    app.state.scripts.load_all()
    op = as_op(app, users)
    r = op.put("/api/v1/automations/report", json={"yaml": CALLS_SCRIPT})
    assert r.status_code == 403 and "disk.sh" in r.json()["detail"]
    set_assignments(app.state.db, "test", "script:disk.sh", [("role", "operator")])
    assert op.put("/api/v1/automations/report", json={"yaml": CALLS_SCRIPT}).status_code == 200


def test_routine_scripts_count_in_deep_refs(app, users):
    load_ups(app)
    doc = app.state.config.get("automation", "ups-on-battery").doc
    assert "scripts/Stop-LabHosts.ps1" in app.state.config.deep_refs(doc).scripts


def test_test_center_checks_routine_scripts(app, users):
    load_ups(app)
    set_assignments(app.state.db, "test", "sequence:lab_safe_shutdown", [("role", "operator")])
    r = as_op(app, users).post("/api/v1/test-center/run", json={
        "kind": "automation", "id": "via-routine", "yaml": CALLS_ROUTINE})
    assert r.status_code == 403  # the routine's switch and script aren't the operator's


def test_bad_script_ref_is_config_error(app, users):
    bad = CALLS_SCRIPT.replace("scripts/disk.sh", "scripts/../../etc/passwd.sh")
    r = as_admin(app, users).put("/api/v1/automations/report", json={"yaml": bad})
    assert r.status_code == 422 and "ref" in r.json()["detail"]


def test_test_center_uses_header_sample(app, users):
    load_ups(app)
    r = as_admin(app, users).post("/api/v1/test-center/run", json={
        "kind": "automation", "id": "ups-on-battery",
        "trigger": {"type": "state", "entity": "binary_sensor.ups_on_battery", "to": "on"},
        "states": {"sensor.ups_battery_runtime_min": "12"}})
    details = [s["detail"] for s in r.json()["trace"]["steps"]]
    assert "What if: notify: Lab shutdown: 3 hosts stopped." in details


def test_body_sample_overrides_header(app, users):
    load_ups(app)
    r = as_admin(app, users).post("/api/v1/test-center/run", json={
        "kind": "automation", "id": "ups-on-battery",
        "trigger": {"type": "state", "entity": "binary_sensor.ups_on_battery", "to": "on"},
        "states": {"sensor.ups_battery_runtime_min": "12"},
        "script_samples": {"scripts/Stop-LabHosts.ps1": {"status": "nothing to stop"}}})
    details = [s["detail"] for s in r.json()["trace"]["steps"]]
    assert "What if: notify: Lab shutdown: nothing to stop." in details
