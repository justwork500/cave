from pathlib import Path

from cave import audit
from cave.access.evaluate import can_control
from cave.access.items import get_assignments, get_item, set_assignments, upsert_item
from cave.access.model import Item
from cave.api.deps import principal_for_user
from tests.access_fixtures import LAN, LOCAL
from tests.conftest import T0, lan_client, sign_in

FIX = Path(__file__).parent / "fixtures" / "config"

GARAGE_AUTOMATION = """\
automation:
  id: close-garage
  name: Close garage at night
  triggers:
    - type: time
      at: "22:00"
  actions:
    - type: call
      target: cover.garage_door
      command: close
"""

KIDS_AUTOMATION = """\
# my kids light automation
automation:
  id: kids-off
  name: Kids light off
  triggers:
    - type: time
      at: "20:00"
  actions:
    - type: call
      target: light.kids_room
      command: turn_off
"""


def put_file(app, kind: str, name: str, text: str) -> Path:
    folder = app.state.settings.config_dir / f"{kind}s"
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / f"{name}.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def as_admin(app, users):
    return sign_in(lan_client(app), "admin", "pw-admin-1234", users.admin_totp)


def as_op(app, users):
    return sign_in(lan_client(app), "op", "pw-op-1234", users.op_totp)


def test_load_creates_items_with_defaults_and_entities(app, users):
    put_file(app, "dashboard", "home", (FIX / "dashboards" / "home.yaml").read_text(encoding="utf-8"))
    put_file(app, "automation", "kids-off", KIDS_AUTOMATION)
    app.state.config.load_all()
    home = get_item(app.state.db, "dashboard:home")
    assert home is not None and home.name == "Home" and home.builtin  # the built-in Home dashboard item
    kids = get_item(app.state.db, "automation:kids-off")
    assert kids is not None and kids.kind == "action" and kids.visibility == "restrict" and kids.others_see == "locked"
    rows = app.state.db.execute("SELECT entity_id FROM item_entities WHERE item_id='dashboard:home'").fetchall()
    assert {r[0] for r in rows} == {"light.living_room", "sensor.ups_load_pct", "sensor.ups_battery_runtime_min"}
    # an action grants control only through running it, never directly
    assert app.state.db.execute(
        "SELECT count(*) FROM item_entities WHERE item_id='automation:kids-off'").fetchone()[0] == 0


def test_reload_never_changes_access(app, users):
    put_file(app, "automation", "kids-off", KIDS_AUTOMATION)
    app.state.config.load_all()
    item = get_item(app.state.db, "automation:kids-off")
    upsert_item(app.state.db, "test", Item(item.id, item.kind, item.name, visibility="show"))
    set_assignments(app.state.db, "test", item.id, [("role", "household")])
    put_file(app, "automation", "kids-off", KIDS_AUTOMATION.replace("Kids light off", "Kids lights off"))
    app.state.config.load_all()
    after = get_item(app.state.db, "automation:kids-off")
    assert after.visibility == "show" and after.name == "Kids lights off"
    assert get_assignments(app.state.db, item.id) == [("role", "household")]
    assert "config.file_changed" in [e["action"] for e in audit.list_entries(app.state.db)]


def test_broken_file_listed_with_line_and_item_kept(app, users):  # Review Focus 5
    put_file(app, "automation", "kids-off", KIDS_AUTOMATION)
    app.state.config.load_all()
    put_file(app, "automation", "kids-off", KIDS_AUTOMATION.replace("command: turn_off", "comand: turn_off"))
    app.state.config.load_all()
    assert app.state.config.errors["automations/kids-off.yaml"].startswith("kids-off.yaml:11: ")
    assert get_item(app.state.db, "automation:kids-off") is not None
    assert app.state.config.get("automation", "kids-off") is None
    c = as_admin(app, users)
    assert "automations/kids-off.yaml" in c.get("/api/v1/config/errors").json()


def test_deleted_file_keeps_item(app, users):
    p = put_file(app, "automation", "kids-off", KIDS_AUTOMATION)
    app.state.config.load_all()
    p.unlink()
    app.state.config.load_all()
    assert get_item(app.state.db, "automation:kids-off") is not None and app.state.config.get("automation", "kids-off") is None


def test_save_guard_blocks_operator(app, users, garage):
    r = as_op(app, users).put("/api/v1/automations/close-garage", json={"yaml": GARAGE_AUTOMATION})
    assert r.status_code == 403 and "cover.garage_door" in r.json()["detail"]
    assert app.state.config.get("automation", "close-garage") is None


def test_operator_can_save_what_they_control(app, users, garage):
    set_assignments(app.state.db, "test", "dashboard:kids", [("role", "operator")])
    r = as_op(app, users).put("/api/v1/automations/kids-off", json={"yaml": KIDS_AUTOMATION})
    assert r.status_code == 200, r.text
    assert app.state.config.get("automation", "kids-off") is not None


def test_operator_cannot_overwrite_file_with_foreign_device(app, users, garage):  # Review Focus 1
    put_file(app, "automation", "close-garage", GARAGE_AUTOMATION)  # hand-written by someone with access
    app.state.config.load_all()
    set_assignments(app.state.db, "test", "dashboard:kids", [("role", "operator")])
    harmless = KIDS_AUTOMATION.replace("id: kids-off", "id: close-garage")
    r = as_op(app, users).put("/api/v1/automations/close-garage", json={"yaml": harmless})
    assert r.status_code == 403 and "cover.garage_door" in r.json()["detail"]
    assert as_op(app, users).delete("/api/v1/automations/close-garage").status_code == 403


def test_dynamic_template_refused_for_non_admin_allowed_for_admin(app, users, garage):  # Review Focus 2
    set_assignments(app.state.db, "test", "dashboard:kids", [("role", "operator")])
    text = KIDS_AUTOMATION + "    - type: notify\n      message: \"{{ states('cover.' ~ 'garage_door') }}\"\n"
    r = as_op(app, users).put("/api/v1/automations/kids-off", json={"yaml": text})
    assert r.status_code == 403 and "name devices directly" in r.json()["detail"]
    assert as_admin(app, users).put("/api/v1/automations/kids-off", json={"yaml": text}).status_code == 200


def test_template_read_counts_for_guard(app, users, garage):
    set_assignments(app.state.db, "test", "dashboard:kids", [("role", "operator")])
    text = KIDS_AUTOMATION + "    - type: notify\n      message: \"{{ states('cover.garage_door') }}\"\n"
    r = as_op(app, users).put("/api/v1/automations/kids-off", json={"yaml": text})
    assert r.status_code == 403 and "cover.garage_door" in r.json()["detail"]


def test_sequence_use_required(app, users, garage):
    put_file(app, "sequence", "lab_safe_shutdown", (FIX / "sequences" / "lab_safe_shutdown.yaml").read_text())
    app.state.config.load_all()
    set_assignments(app.state.db, "test", "dashboard:kids", [("role", "operator")])
    text = KIDS_AUTOMATION + "    - type: sequence\n      ref: sequence.lab_safe_shutdown\n"
    c = as_op(app, users)
    assert c.put("/api/v1/automations/kids-off", json={"yaml": text}).status_code == 403
    set_assignments(app.state.db, "test", "sequence:lab_safe_shutdown", [("role", "operator")])
    assert c.put("/api/v1/automations/kids-off", json={"yaml": text}).status_code == 200


def test_save_writes_text_verbatim_with_comments(app, users):
    c = as_admin(app, users)
    assert c.put("/api/v1/automations/kids-off", json={"yaml": KIDS_AUTOMATION}).status_code == 200
    path = app.state.settings.config_dir / "automations" / "kids-off.yaml"
    assert path.read_text(encoding="utf-8") == KIDS_AUTOMATION
    entry = audit.list_entries(app.state.db)[0]
    assert entry["action"] == "config.save" and entry["new"] == KIDS_AUTOMATION


def test_id_must_match_filename(app, users):
    r = as_admin(app, users).put("/api/v1/automations/other-name", json={"yaml": KIDS_AUTOMATION})
    assert r.status_code == 422 and "other-name" in r.json()["detail"]


def test_bad_url_id_refused(app, users):
    assert as_admin(app, users).put("/api/v1/automations/..%2Fevil", json={"yaml": KIDS_AUTOMATION}).status_code in (
        404, 405, 422)  # 405: the decoded path only matches the console's GET-only fallback
    assert not list(app.state.settings.config_dir.rglob("evil*"))


def test_invalid_yaml_422_with_line(app, users):
    r = as_admin(app, users).put("/api/v1/automations/kids-off",
                                 json={"yaml": KIDS_AUTOMATION.replace("command:", "comand:")})
    assert r.status_code == 422 and r.json()["detail"].startswith("kids-off.yaml:11: ")


def test_get_yaml_needs_control_of_every_referenced_entity(app, users, garage):
    put_file(app, "automation", "close-garage", GARAGE_AUTOMATION)
    app.state.config.load_all()
    set_assignments(app.state.db, "test", "automation:close-garage", [("role", "operator")])
    c = as_op(app, users)
    listed = {i["id"]: i for i in c.get("/api/v1/automations").json()}
    assert listed["close-garage"]["allowed"] is True
    assert c.get("/api/v1/automations/close-garage").status_code == 403
    assert as_admin(app, users).get("/api/v1/automations/close-garage").json()["yaml"] == GARAGE_AUTOMATION


def test_dashboard_entities_grant_control(app, users, garage):
    text = (FIX / "dashboards" / "home.yaml").read_text().replace("light.living_room", "cover.garage_door")
    text = text.replace("title: Home", "title: Garage")
    assert as_admin(app, users).put("/api/v1/dashboards/garage2", json={"yaml": text}).status_code == 200
    set_assignments(app.state.db, "test", "dashboard:garage2", [("user", users.sam.id)])
    sam = principal_for_user(app.state.db, users.sam, T0)
    assert can_control(app.state.db, sam, "cover.garage_door", LAN, LOCAL)


def test_errors_and_reload_permissions(app, users):
    c = as_op(app, users)
    assert c.post("/api/v1/config/reload").status_code == 403
    assert c.get("/api/v1/config/errors").status_code == 403
    a = as_admin(app, users)
    assert a.post("/api/v1/config/reload").status_code == 204
    assert a.get("/api/v1/config/errors").json() == {}


def test_schema_endpoint(app, users):
    c = sign_in(lan_client(app), "sam", "pw-sam-1234")
    assert c.get("/api/v1/schemas/automation.json").json()["title"] == "AutomationFile"
    assert c.get("/api/v1/schemas/nope.json").status_code == 404


def test_create_refuses_an_existing_file(app, users):
    """New automations and recipes save with ?create=true, so they can't silently replace one that exists."""
    c = as_admin(app, users)
    assert c.put("/api/v1/automations/kids-off?create=true", json={"yaml": KIDS_AUTOMATION}).status_code == 200
    changed = KIDS_AUTOMATION.replace("20:00", "21:00")
    r = c.put("/api/v1/automations/kids-off?create=true", json={"yaml": changed})
    assert r.status_code == 409 and "already taken" in r.json()["detail"]
    path = app.state.settings.config_dir / "automations" / "kids-off.yaml"
    assert path.read_text(encoding="utf-8") == KIDS_AUTOMATION
    assert c.put("/api/v1/automations/kids-off", json={"yaml": changed}).status_code == 200  # editing still works
