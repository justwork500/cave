"""Tests for the final whole-branch review findings."""
from datetime import UTC, datetime, timedelta

import pytest
from starlette.websockets import WebSocketDisconnect

from cave.access.items import set_item_entities
from cave.auth.users import LoginError, check_password, create_user
from cave.state import QUEUE_SIZE, EventBus
from tests.conftest import T0, lan_client, sign_in
from tests.test_ws import connect, ping, subscribe


# 1 (Critical): MFA brute force
def test_mfa_wrong_codes_drop_pending_and_count_toward_lockout(client, users):
    r = client.post("/api/v1/auth/login", json={"username": "admin", "password": "pw-admin-1234"})
    assert r.json() == {"mfa_required": True}
    for _ in range(5):
        assert client.post("/api/v1/auth/mfa", json={"code": "000000"}).status_code == 401
    r = client.post("/api/v1/auth/mfa", json={"code": users.admin_totp.now()})
    assert r.status_code == 401 and r.json()["detail"] == "Sign in again."
    r = client.post("/api/v1/auth/login", json={"username": "admin", "password": "pw-admin-1234"})
    assert r.status_code == 401 and "Too many attempts" in r.json()["detail"]


# 2: last-Admin rule via expires_at
def test_last_admin_cannot_be_expired(client, users):
    sign_in(client, "admin", "pw-admin-1234", users.admin_totp)
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    assert client.patch(f"/api/v1/users/{users.admin.id}", json={"expires_at": past}).status_code == 409


def test_expired_admin_does_not_count_as_other_admin(app, client, users):
    sign_in(client, "admin", "pw-admin-1234", users.admin_totp)
    other = create_user(app.state.db, "test", "admin2", "pw-admin2-1234", "admin")
    app.state.db.execute("UPDATE users SET expires_at=? WHERE id=?", ("2000-01-01T00:00:00+00:00", other.id))
    assert client.patch(f"/api/v1/users/{users.admin.id}", json={"enabled": False}).status_code == 409


# 3: sign-out / expiry closes the live feed
def test_logout_closes_websocket(client, users, garage):
    sign_in(client, "sam", "pw-sam-1234")
    with connect(client) as ws:
        subscribe(ws)
        other = lan_client(client.app)
        other.cookies.set("cave_session", client.cookies.get("cave_session"), domain="testserver.local")
        assert other.post("/api/v1/auth/logout").status_code == 204
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
        assert e.value.code == 4401


def test_expired_user_websocket_closes_on_recheck(app, client, users, garage, monkeypatch):
    import cave.api.ws as ws_mod

    monkeypatch.setattr(ws_mod, "RECHECK_SECONDS", 0)
    sign_in(client, "sam", "pw-sam-1234")
    with connect(client) as ws:
        subscribe(ws)
        app.state.db.execute("UPDATE users SET expires_at=? WHERE id=?", ("2000-01-01T00:00:00+00:00", users.sam.id))
        ping(ws)
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
        assert e.value.code == 4401


# 4: cross-site WebSocket hijacking
def test_websocket_rejects_foreign_origin(client, users, garage):
    sign_in(client, "sam", "pw-sam-1234")
    session = client.cookies.get("cave_session")
    headers = {"cookie": f"cave_session={session}", "origin": "https://evil.example"}
    with client.websocket_connect("/api/v1/ws", headers=headers) as ws, pytest.raises(WebSocketDisconnect) as e:
        ws.receive_json()
    assert e.value.code == 4403


def test_websocket_accepts_own_origin(client, users, garage):
    sign_in(client, "sam", "pw-sam-1234")
    session = client.cookies.get("cave_session")
    headers = {"cookie": f"cave_session={session}", "origin": "https://testserver"}
    with client.websocket_connect("/api/v1/ws", headers=headers) as ws:
        ping(ws)
        assert ws.receive_json()["type"] == "pong"


# 5: overflow must not silently drop control events
def test_overflow_replaces_queue_with_overflow_marker():
    bus = EventBus()
    q = bus.subscribe()
    for i in range(QUEUE_SIZE + 1):
        bus.publish({"type": "state_changed", "n": i})
    assert q.qsize() == 1 and q.get_nowait() == {"type": "overflow"}


def test_overflow_closes_socket(app, client, users, garage):
    sign_in(client, "sam", "pw-sam-1234")
    with connect(client) as ws:
        subscribe(ws)
        app.state.bus.publish({"type": "overflow"})
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
        assert e.value.code == 4408


# 6: set_item_entities notifies live sockets by itself
def test_set_item_entities_publishes_access_changed():
    bus = EventBus()
    q = bus.subscribe()

    class FakeDb:
        def transaction(self):
            import contextlib

            @contextlib.contextmanager
            def cm():
                class C:
                    def execute(self, *a): ...
                    def executemany(self, *a): ...
                yield C()
            return cm()

    set_item_entities(FakeDb(), "dashboard:kids", [], bus=bus)  # type: ignore[arg-type]
    assert q.get_nowait() == {"type": "access_changed"}


# re-graded minor 8: blocked attempts must not extend a lockout forever
def test_attempts_while_locked_do_not_extend_lockout(db):
    create_user(db, "system", "sam", "correct horse", "household")
    for _ in range(5):
        with pytest.raises(LoginError):
            check_password(db, "sam", "nope", "1.1.1.1", T0)
    for minute in range(1, 16):
        with pytest.raises(LoginError, match="Too many attempts"):
            check_password(db, "sam", "nope", "1.1.1.1", T0 + timedelta(minutes=minute, seconds=-30))
    assert check_password(db, "sam", "correct horse", "1.1.1.1", T0 + timedelta(minutes=16)).username == "sam"
