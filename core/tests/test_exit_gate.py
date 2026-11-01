"""Phase 1 exit gate, item 2, end to end through the HTTP API: a real dashboard file, restricted by an Admin.

The other refusals are pinned closer to the code (see docs/exit-gate.md); this one checks the whole path."""

from tests.access_fixtures import LAN
from tests.conftest import lan_client, sign_in

GARAGE = """\
dashboard:
  title: Garage Door Control
  views:
    - id: main
      title: Garage
      sections:
        - title: Door
          cards:
            - type: tile
              entity: cover.garage_door
"""


def test_household_browser_cannot_open_garage_dashboard(app, users, garage):
    folder = app.state.settings.config_dir / "dashboards"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "garage-door.yaml").write_text(GARAGE, encoding="utf-8")
    admin = sign_in(lan_client(app), "admin", "pw-admin-1234", users.admin_totp)
    assert admin.post("/api/v1/config/reload").status_code == 204
    item = "dashboard:garage-door"
    assert admin.patch(f"/api/v1/items/{item}", json={"visibility": "restrict", "network": "local"}).status_code == 200
    assert admin.put(f"/api/v1/items/{item}/assignments", json=[{"kind": "screen", "id": "garage"}]).status_code == 200
    assert admin.get("/api/v1/dashboards/garage-door/view").status_code == 200  # it loads, for those allowed

    sam = sign_in(lan_client(app), "sam", "pw-sam-1234")
    assert sam.get("/api/v1/dashboards/garage-door/view").status_code == 403
    listed = {i["id"]: i for i in sam.get("/api/v1/items").json()}
    assert listed[item]["allowed"] is False  # seen as locked, not usable
    assert sam.post("/api/v1/entities/cover.garage_door/commands/open", json={}).status_code == 403
    assert garage.calls == []
    assert LAN  # the browser is on the LAN: being on the network grants nothing by itself
