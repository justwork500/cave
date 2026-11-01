from datetime import UTC, datetime

from cave.access.items import set_assignments, set_item_entities, upsert_item
from cave.access.model import Item
from tests.conftest import lan_client, sign_in
from tests.test_screen_auth import approved_screen, screen_client

KIDS = """\
dashboard:
  title: Kids
  views:
    - id: main
      title: Kids
      sections:
        - title: Room
          cards:
            - type: tile
              entity: light.kids_room
            - type: tile
              entity: cover.garage_door
            - type: markdown
              content: "Light is {{ states('light.kids_room') }}, garage is {{ states('cover.garage_door') }}"
            - type: button
              name: Bedtime
              action: sequence.bedtime
            - type: button
              name: Lights off
              entity: light.kids_room
              command: turn_off
"""


def load_kids(app):
    d = app.state.settings.config_dir / "dashboards"
    d.mkdir(exist_ok=True)
    (d / "kids.yaml").write_text(KIDS, encoding="utf-8")
    app.state.config.load_all()


def cards(view):
    return [c for v in view["views"] for s in v["sections"] for c in s["cards"]]


def as_sam(app):
    return sign_in(lan_client(app), "sam", "pw-sam-1234")


def test_view_locks_restricted_tile_and_markdown(app, users, garage):  # Review Focus 1
    load_kids(app)
    # every card's device is granted by the dashboard itself; narrow it to reach the locked path
    set_item_entities(app.state.db, "dashboard:kids", ["light.kids_room"], bus=app.state.bus)
    view = as_sam(app).get("/api/v1/dashboards/kids/view").json()
    tile, garage_tile, md, *_ = cards(view)
    assert tile["locked"] is False and tile["entity"]["state"] == "off"
    assert garage_tile["locked"] is True and garage_tile["entity"]["restricted"] is True
    assert md["text"] == "Light is off, garage is restricted"
    assert "closed" not in str(view)


def test_dashboard_cards_grant_their_devices(app, users, garage):
    load_kids(app)
    view = as_sam(app).get("/api/v1/dashboards/kids/view").json()
    assert cards(view)[1]["locked"] is False  # putting the garage on Kids gave Kids the garage


def test_view_needs_dashboard_use(app, users, garage):
    load_kids(app)
    set_assignments(app.state.db, "test", "dashboard:kids", [])
    assert as_sam(app).get("/api/v1/dashboards/kids/view").status_code == 403
    assert as_sam(app).get("/api/v1/dashboards/nope/view").status_code == 404


def test_screen_gets_its_dashboard_view(app, users, garage):
    load_kids(app)
    set_assignments(app.state.db, "test", "dashboard:kids", [("screen", "garage")])
    c = screen_client(app, "garage", approved_screen(app.state.db, "garage"))
    assert c.get("/api/v1/dashboards/kids/view").status_code == 200


def test_button_allowed_flags(app, users, garage):
    load_kids(app)
    upsert_item(app.state.db, "test", Item("sequence:bedtime", "action", "Bedtime", others_see="none"))
    view = as_sam(app).get("/api/v1/dashboards/kids/view").json()
    names = [c.get("name") for c in cards(view) if c["type"] == "button"]
    assert names == ["Lights off"]  # Bedtime isn't listed for sam, so it's left out
    set_assignments(app.state.db, "test", "sequence:bedtime", [("user", users.sam.id)])
    buttons = [c for c in cards(as_sam(app).get("/api/v1/dashboards/kids/view").json()) if c["type"] == "button"]
    assert [(b["name"], b["allowed"]) for b in buttons] == [("Bedtime", True), ("Lights off", True)]


def test_default_dashboard_choice(app, users, garage):
    home = app.state.settings.config_dir / "dashboards" / "home.yaml"
    starter = home.read_text(encoding="utf-8")
    home.unlink()  # an Admin deleted Home
    load_kids(app)
    assert as_sam(app).get("/api/v1/dashboards/default").json() == {"slug": "kids"}
    home.write_text(starter, encoding="utf-8")
    app.state.config.load_all()
    assert as_sam(app).get("/api/v1/dashboards/default").json() == {"slug": "home"}
    op = sign_in(lan_client(app), "op", "pw-op-1234", users.op_totp)
    assert op.get("/api/v1/dashboards/default").json() == {"slug": None}


def test_summary_only_your_tiles(app, users, garage):
    app.state.states.set("light.kids_room", "unavailable")
    app.state.db.execute(
        "INSERT INTO automation_traces (item_id, test, started_at, finished_at, outcome, trace) VALUES "
        "('automation:x', 0, ?, ?, 'failed', '{}')", (datetime.now(UTC).isoformat(), datetime.now(UTC).isoformat()))
    admin = sign_in(lan_client(app), "admin", "pw-admin-1234", users.admin_totp).get("/api/v1/summary").json()
    assert admin["unavailable"] == 1 and admin["failures_24h"] == 1 and admin["screens_pending"] == 0
    assert admin["mqtt"]["status"] == "disabled"
    op = sign_in(lan_client(app), "op", "pw-op-1234", users.op_totp).get("/api/v1/summary").json()
    assert set(op) == {"mqtt", "unavailable", "failures_24h"} and op["unavailable"] == 0  # can't control it
    assert as_sam(app).get("/api/v1/summary").json() == {}


def test_signin_log_permission_and_labels(app, users):
    lan_client(app).post("/api/v1/auth/login", json={"username": "sam", "password": "nope"})
    sign_in(lan_client(app), "sam", "pw-sam-1234")
    assert as_sam(app).get("/api/v1/signin-log").status_code == 403
    aud = sign_in(lan_client(app), "aud", "pw-aud-1234")
    rows = aud.get("/api/v1/signin-log?limit=50").json()
    assert {"wrong password or code", "signed in"} <= {r["result"] for r in rows if r["username"] == "sam"}


def test_markdown_template_error_is_friendly(app, users, garage):
    load_kids(app)
    text = KIDS.replace("Light is {{ states('light.kids_room') }}", "{{ nothing_here }}")
    (app.state.settings.config_dir / "dashboards" / "kids.yaml").write_text(text, encoding="utf-8")
    app.state.config.load_all()
    md = next(c for c in cards(as_sam(app).get("/api/v1/dashboards/kids/view").json()) if c["type"] == "markdown")
    assert md["text"] == "(this card couldn't be shown)"
