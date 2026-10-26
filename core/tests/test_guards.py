import pytest

from cave.access.evaluate import AccessDenied, assert_can_save, can_control
from cave.api.deps import principal_for_user
from tests.access_fixtures import LAN, LOCAL, WAN, screen
from tests.conftest import T0, sign_in


def test_kids_dashboard_cannot_open_garage(app, users, garage):
    sam = principal_for_user(app.state.db, users.sam, T0)
    assert not can_control(app.state.db, sam, "cover.garage_door", LAN, LOCAL)
    assert can_control(app.state.db, sam, "light.kids_room", LAN, LOCAL)


def test_garage_tablet_only_on_lan(app, garage):
    tablet = screen("garage")
    assert can_control(app.state.db, tablet, "cover.garage_door", LAN, LOCAL)
    assert not can_control(app.state.db, tablet, "cover.garage_door", WAN, LOCAL)
    assert not can_control(app.state.db, screen("other"), "cover.garage_door", LAN, LOCAL)


def test_entity_in_no_item_is_admin_only(app, users, garage):
    sam = principal_for_user(app.state.db, users.sam, T0)
    admin = principal_for_user(app.state.db, users.admin, T0)
    assert not can_control(app.state.db, sam, "switch.nowhere", LAN, LOCAL)
    assert can_control(app.state.db, admin, "switch.nowhere", WAN, LOCAL)


def test_command_route_refuses_and_does_not_call_handler(client, users, garage):
    sign_in(client, "sam", "pw-sam-1234")
    r = client.post("/api/v1/entities/cover.garage_door/commands/open", json={})
    assert r.status_code == 403 and r.json() == {"detail": "You don't have access to this control."}
    assert garage.calls == []


def test_command_route_allows_assigned_control(client, users, garage):
    sign_in(client, "sam", "pw-sam-1234")
    r = client.post("/api/v1/entities/light.kids_room/commands/turn_on", json={"brightness": 50})
    assert r.status_code == 202
    assert garage.calls == [("light.kids_room", "turn_on", {"brightness": 50})]


def test_command_route_unknown_entity_404_for_admin(client, users, garage):
    sign_in(client, "admin", "pw-admin-1234", users.admin_totp)
    assert client.post("/api/v1/entities/light.nope/commands/turn_on", json={}).status_code == 404


def test_command_route_requires_sign_in(client, garage):
    assert client.post("/api/v1/entities/light.kids_room/commands/turn_on", json={}).status_code == 401


def test_save_guard_blocks_back_door(app, users, garage):
    op = principal_for_user(app.state.db, users.op, T0)
    with pytest.raises(AccessDenied) as e:
        assert_can_save(app.state.db, op, ["cover.garage_door", "light.kids_room"], LAN, LOCAL)
    assert "cover.garage_door" in str(e.value) and "light.kids_room" in str(e.value)


def test_save_guard_allows_what_you_control(app, users, garage):
    sam = principal_for_user(app.state.db, users.sam, T0)
    assert_can_save(app.state.db, sam, ["light.kids_room"], LAN, LOCAL)


def test_admin_can_save_anything(app, users, garage):
    admin = principal_for_user(app.state.db, users.admin, T0)
    assert_can_save(app.state.db, admin, ["cover.garage_door"], WAN, LOCAL)
