import pytest
from starlette.websockets import WebSocketDisconnect

from cave.access.items import set_item_entities
from tests.conftest import sign_in


def connect(client):
    # TestClient speaks ws:// (not wss://), so it withholds the Secure cookie; pass it explicitly
    session = client.cookies.get("cave_session")
    return client.websocket_connect("/api/v1/ws", headers={"cookie": f"cave_session={session}"} if session else {})


def subscribe(ws):
    ws.send_json({"id": 1, "type": "subscribe", "events": ["state_changed"]})
    assert ws.receive_json() == {"id": 1, "type": "result", "success": True}


def ping(ws, msg_id=99):
    ws.send_json({"id": msg_id, "type": "ping"})


def test_ws_requires_sign_in(client, garage):
    with connect(client) as ws, pytest.raises(WebSocketDisconnect) as e:
        ws.receive_json()
    assert e.value.code == 4401


def test_events_filtered(app, client, users, garage):
    sign_in(client, "sam", "pw-sam-1234")
    with connect(client) as ws:
        subscribe(ws)
        app.state.states.set("cover.garage_door", "open")
        app.state.states.set("light.kids_room", "on")
        msg = ws.receive_json()
        assert msg["type"] == "event" and msg["event"]["entity_id"] == "light.kids_room"


def test_admin_gets_all_events(app, client, users, garage):
    sign_in(client, "admin", "pw-admin-1234", users.admin_totp)
    with connect(client) as ws:
        subscribe(ws)
        app.state.states.set("cover.garage_door", "open")
        assert ws.receive_json()["event"]["entity_id"] == "cover.garage_door"


def test_no_events_before_subscribe(app, client, users, garage):
    sign_in(client, "sam", "pw-sam-1234")
    with connect(client) as ws:
        app.state.states.set("light.kids_room", "on")
        ping(ws)
        assert ws.receive_json() == {"id": 99, "type": "pong"}


def test_entity_removed_from_item_stops_events(app, client, users, garage):  # Review Focus 4
    sign_in(client, "sam", "pw-sam-1234")
    with connect(client) as ws:
        subscribe(ws)
        app.state.states.set("light.kids_room", "on")
        assert ws.receive_json()["event"]["new"] == "on"
        set_item_entities(app.state.db, "dashboard:kids", [])
        app.state.bus.publish({"type": "access_changed"})
        app.state.states.set("light.kids_room", "off")
        ping(ws)
        assert ws.receive_json() == {"id": 99, "type": "pong"}
    assert client.get("/api/v1/states/light.kids_room").json()["restricted"] is True


def test_disabled_user_socket_closes(app, client, users, garage):  # Review Focus 3
    sign_in(client, "sam", "pw-sam-1234")
    with connect(client) as ws:
        subscribe(ws)
        app.state.bus.publish({"type": "principal_disabled", "user_id": users.sam.id})
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
        assert e.value.code == 4401


def test_ws_command_respects_guard(client, users, garage):
    sign_in(client, "sam", "pw-sam-1234")
    with connect(client) as ws:
        ws.send_json({"id": 5, "type": "command", "entity_id": "cover.garage_door", "command": "open", "args": {}})
        assert ws.receive_json() == {
            "id": 5, "type": "result", "success": False, "error": "You don't have access to this control."
        }
        ws.send_json({"id": 6, "type": "command", "entity_id": "light.kids_room", "command": "turn_on", "args": {}})
        assert ws.receive_json() == {"id": 6, "type": "result", "success": True}
    assert garage.calls == [("light.kids_room", "turn_on", {})]
