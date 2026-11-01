import threading

import pyotp
from fastapi.testclient import TestClient

from cave.api.setup import ensure_setup_code
from cave.auth.users import create_user
from tests.conftest import lan_client, sign_in

PW = "a-long-owner-password"


def fresh(app) -> tuple[TestClient, str]:
    code = ensure_setup_code(app.state.db)
    assert code is not None
    return lan_client(app), code


def owner(c, code, username="owner"):
    return c.post("/api/v1/setup", json={"code": code, "username": username, "password": PW,
                                         "display_name": "The Owner"})


def test_setup_needed_only_without_users(app):
    c = lan_client(app)
    assert c.get("/api/v1/setup").json() == {"needed": True}
    create_user(app.state.db, "test", "x", "pw-x-12345678", "household")
    assert c.get("/api/v1/setup").json() == {"needed": False}


def test_setup_code_required(app):  # Review Focus 2
    c, code = fresh(app)
    assert c.post("/api/v1/setup", json={"username": "o", "password": PW, "display_name": "O"}).status_code == 422
    r = owner(c, "WRONG-CODE-0000-0000")
    assert r.status_code == 403 and r.json() == {"detail": "That setup code isn't right."}
    r = owner(c, code)
    assert r.status_code == 200 and len(r.json()["recovery_codes"]) == 10
    assert r.json()["provisioning_uri"].startswith("otpauth://")


def test_setup_refused_once_a_user_exists(app):  # Review Focus 2
    c, code = fresh(app)
    owner(c, code)
    assert ensure_setup_code(app.state.db) is None
    assert owner(lan_client(app), code, "second").status_code == 409


def test_setup_then_mfa_signs_in(app):
    c, code = fresh(app)
    uri = owner(c, code).json()["provisioning_uri"]
    assert c.get("/api/v1/me").status_code == 401
    assert c.post("/api/v1/auth/mfa", json={"code": pyotp.parse_uri(uri).now()}).status_code == 200
    me = c.get("/api/v1/me").json()
    assert me["role"] == "admin" and me["has_totp"] is True and "section:users" in me["sections"]


def test_short_password_refused(app):
    c, code = fresh(app)
    r = c.post("/api/v1/setup", json={"code": code, "username": "o", "password": "short", "display_name": "O"})
    assert r.status_code == 422


def test_concurrent_setup_one_wins(app):
    _, code = fresh(app)
    results = []

    def go(name):
        results.append(owner(lan_client(app), code, name).status_code)

    threads = [threading.Thread(target=go, args=(f"o{i}",)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == [200, 409, 409, 409] or sorted(results).count(200) == 1
    assert app.state.db.execute("SELECT count(*) FROM users").fetchone()[0] == 1


def test_operator_without_totp_enrolls_at_login(app, users):
    create_user(app.state.db, "test", "newop", "pw-newop-1234", "operator")
    c = lan_client(app)
    r = c.post("/api/v1/auth/login", json={"username": "newop", "password": "pw-newop-1234"})
    assert r.json() == {"mfa_required": True, "mfa_setup": True}
    setup = c.post("/api/v1/auth/mfa/setup").json()
    assert len(setup["recovery_codes"]) == 10
    assert c.post("/api/v1/auth/mfa", json={"code": pyotp.parse_uri(setup["provisioning_uri"]).now()}).status_code == 200
    assert c.get("/api/v1/me").json()["has_totp"] is True


def test_mfa_setup_needs_pending_and_no_totp(app, users):
    c = lan_client(app)
    assert c.post("/api/v1/auth/mfa/setup").status_code == 401
    c.post("/api/v1/auth/login", json={"username": "admin", "password": "pw-admin-1234"})  # already has TOTP
    assert c.post("/api/v1/auth/mfa/setup").status_code == 409


def test_me_lists_sections(app, users):
    op = sign_in(lan_client(app), "op", "pw-op-1234", users.op_totp).get("/api/v1/me").json()
    assert set(op["sections"]) == {"section:devices", "section:automations", "section:scripts", "section:dashboards"}
    assert sign_in(lan_client(app), "sam", "pw-sam-1234").get("/api/v1/me").json()["sections"] == []


def test_password_change_ends_other_sessions(app, users):
    a = sign_in(lan_client(app), "sam", "pw-sam-1234")
    b = sign_in(lan_client(app), "sam", "pw-sam-1234")
    assert a.post("/api/v1/me/password", json={"current": "wrong", "new": "a-brand-new-password"}).status_code == 403
    assert a.post("/api/v1/me/password", json={"current": "pw-sam-1234", "new": "short"}).status_code == 422
    assert a.post("/api/v1/me/password", json={"current": "pw-sam-1234",
                                               "new": "a-brand-new-password"}).status_code == 204
    assert a.get("/api/v1/me").status_code == 200  # this session stays
    assert b.get("/api/v1/me").status_code == 401  # the other one ends
    assert lan_client(app).post("/api/v1/auth/login", json={"username": "sam",
                                                            "password": "a-brand-new-password"}).status_code == 200


def test_each_start_gets_a_fresh_code(app):
    first = ensure_setup_code(app.state.db)
    second = ensure_setup_code(app.state.db)  # CAVE restarted before anyone set it up
    assert first and second and first != second and len(second.split("-")) == 4
    assert owner(lan_client(app), first).status_code == 403
    assert owner(lan_client(app), second).status_code == 200


def test_interrupted_enrollment_can_start_again(app):
    """The owner closes the tab before scanning the QR code: signing in again restarts enrollment."""
    c, code = fresh(app)
    first = owner(c, code).json()
    c2 = lan_client(app)
    r = c2.post("/api/v1/auth/login", json={"username": "owner", "password": PW})
    assert r.json() == {"mfa_required": True, "mfa_setup": True}
    again = c2.post("/api/v1/auth/mfa/setup")
    assert again.status_code == 200 and again.json()["provisioning_uri"] != first["provisioning_uri"]
    old = pyotp.parse_uri(first["provisioning_uri"]).now()
    new = pyotp.parse_uri(again.json()["provisioning_uri"]).now()
    if old != new:  # the replaced secret no longer works
        assert c2.post("/api/v1/auth/mfa", json={"code": old}).status_code == 401
    assert c2.post("/api/v1/auth/mfa", json={"code": new}).status_code == 200
    assert c2.get("/api/v1/me").json()["has_totp"] is True
    # once proven, it's set for good
    c3 = lan_client(app)
    assert c3.post("/api/v1/auth/login", json={"username": "owner", "password": PW}).json() == {"mfa_required": True}
    assert c3.post("/api/v1/auth/mfa/setup").status_code == 409


def test_unproven_authenticator_takes_no_recovery_code(app):
    c, code = fresh(app)
    codes = owner(c, code).json()["recovery_codes"]
    assert c.post("/api/v1/auth/mfa", json={"code": codes[0]}).status_code == 401


def test_password_change_is_rate_limited(app, users):
    """A stolen session can't be used to guess the current password without limit."""
    a = sign_in(lan_client(app), "sam", "pw-sam-1234")
    for _ in range(5):
        assert a.post("/api/v1/me/password", json={"current": "guess", "new": "a-brand-new-password"}).status_code == 403
    r = a.post("/api/v1/me/password", json={"current": "pw-sam-1234", "new": "a-brand-new-password"})
    assert r.status_code == 429 and "Too many attempts" in r.json()["detail"]
