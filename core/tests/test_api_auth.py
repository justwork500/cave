from datetime import timedelta

from cave.auth import sessions
from tests.conftest import T0, sign_in


def test_household_login_sets_strict_cookie(client, users):
    r = client.post("/api/v1/auth/login", json={"username": "sam", "password": "pw-sam-1234"})
    assert r.json() == {"mfa_required": False}
    c = r.headers["set-cookie"].lower()
    assert "cave_session=" in c and "httponly" in c and "secure" in c and "samesite=strict" in c
    assert client.get("/api/v1/me").json()["username"] == "sam"


def test_wrong_password_401_with_message(client, users):
    r = client.post("/api/v1/auth/login", json={"username": "sam", "password": "nope"})
    assert r.status_code == 401 and r.json() == {"detail": "Wrong username or password."}


def test_admin_needs_second_factor_before_session(client, users):
    r = client.post("/api/v1/auth/login", json={"username": "admin", "password": "pw-admin-1234"})
    assert r.json() == {"mfa_required": True}
    assert client.get("/api/v1/me").status_code == 401
    assert client.post("/api/v1/auth/mfa", json={"code": "nope"}).status_code == 401
    assert client.post("/api/v1/auth/mfa", json={"code": users.admin_totp.now()}).status_code == 200
    assert client.get("/api/v1/me").json()["role"] == "admin"


def test_mfa_without_pending_login_is_refused(client, users):
    assert client.post("/api/v1/auth/mfa", json={"code": users.admin_totp.now()}).status_code == 401


def test_logout_ends_session(client, users):
    sign_in(client, "sam", "pw-sam-1234")
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/me").status_code == 401


def test_session_idle_timeout(db):
    from cave.auth.users import create_user

    u = create_user(db, "system", "sam", "pw-sam-1234", "household")
    sid = sessions.create(db, u.id, T0)
    assert sessions.lookup(db, sid, T0 + timedelta(hours=11), timedelta(hours=12)) == u.id
    assert sessions.lookup(db, sid, T0 + timedelta(hours=23, minutes=1), timedelta(hours=12)) is None


def test_session_end_for_user(db):
    from cave.auth.users import create_user

    u = create_user(db, "system", "sam", "pw-sam-1234", "household")
    sid = sessions.create(db, u.id, T0)
    sessions.end_for_user(db, u.id)
    assert sessions.lookup(db, sid, T0, timedelta(hours=12)) is None
