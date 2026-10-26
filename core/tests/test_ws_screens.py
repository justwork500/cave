from datetime import UTC, datetime, timedelta

import pytest
from starlette.websockets import WebSocketDisconnect

from cave.auth import screens
from tests.conftest import lan_client
from tests.test_screen_auth import approved_screen, screen_client
from tests.test_ws import ping, subscribe


def connect_screen(c):
    # TestClient speaks ws://, so it withholds Secure cookies; pass the screen session explicitly
    return c.websocket_connect("/api/v1/ws", headers={"cookie": f"cave_screen={c.cookies.get('cave_screen')}"})


def test_screen_receives_only_its_entities(app, users, garage):
    c = screen_client(app, "garage", approved_screen(app.state.db, "garage"))
    with connect_screen(c) as ws:
        subscribe(ws)
        app.state.states.set("light.kids_room", "on")
        app.state.states.set("cover.garage_door", "open")
        assert ws.receive_json()["event"]["entity_id"] == "cover.garage_door"


def test_revoked_screen_socket_closes(app, users, garage):  # Review Focus 5
    c = screen_client(app, "garage", approved_screen(app.state.db, "garage"))
    admin = lan_client(app)
    from tests.conftest import sign_in

    sign_in(admin, "admin", "pw-admin-1234", users.admin_totp)
    with connect_screen(c) as ws:
        subscribe(ws)
        assert admin.post("/api/v1/screens/garage/revoke").status_code == 200
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
        assert e.value.code == 4401


def test_screen_socket_closes_after_session_cap(app, users, garage, monkeypatch):
    import cave.api.ws as ws_mod

    monkeypatch.setattr(ws_mod, "RECHECK_SECONDS", 0)
    c = screen_client(app, "garage", approved_screen(app.state.db, "garage"))
    with connect_screen(c) as ws:
        subscribe(ws)
        old = (datetime.now(UTC) - screens.SESSION_MAX_AGE - timedelta(minutes=1)).isoformat()
        app.state.db.execute("UPDATE screen_sessions SET created_at=?", (old,))
        ping(ws)
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
        assert e.value.code == 4401


def test_screen_ws_command_off_network_refused(app, users, garage):
    c = screen_client(app, "garage", approved_screen(app.state.db, "garage"), ip="203.0.113.9")
    with connect_screen(c) as ws:
        ws.send_json({"id": 1, "type": "command", "entity_id": "cover.garage_door", "command": "open", "args": {}})
        assert ws.receive_json()["success"] is False
    assert garage.calls == []


def test_networks_change_applies_to_open_socket(app, users, garage):
    from cave.access import netconfig

    c = screen_client(app, "garage", approved_screen(app.state.db, "garage"))
    with connect_screen(c) as ws:
        ws.send_json({"id": 1, "type": "command", "entity_id": "cover.garage_door", "command": "open", "args": {}})
        assert ws.receive_json()["success"] is True
        netconfig.save(app.state.db, "test", ["10.0.0.0/8"], [])
        app.state.bus.publish({"type": "access_changed"})
        ping(ws)  # handles the queued access change before the next command
        assert ws.receive_json()["type"] == "pong"
        ws.send_json({"id": 2, "type": "command", "entity_id": "cover.garage_door", "command": "open", "args": {}})
        assert ws.receive_json() == {"id": 2, "type": "result", "success": False,
                                     "error": "You don't have access to this control."}
