from datetime import timedelta

import pytest

from cave.auth import screens
from tests.conftest import T0, lan_client
from tests.screen_key import FakeTablet

OPEN_GARAGE = "/api/v1/entities/cover.garage_door/commands/open"


def approved_screen(db, screen_id: str) -> FakeTablet:
    _, code = screens.create(db, "test", screen_id, T0, screen_id=screen_id)
    tablet = FakeTablet()
    screens.enroll(db, code, tablet.spki_b64, T0)
    screens.approve(db, "test", screen_id, T0)
    return tablet


def screen_client(app, screen_id: str, tablet: FakeTablet, ip: str = "192.168.1.5"):
    c = lan_client(app, ip)
    nonce = c.post("/api/v1/screen-auth/challenge", json={"screen_id": screen_id}).json()["nonce"]
    r = c.post("/api/v1/screen-auth/verify",
               json={"screen_id": screen_id, "nonce": nonce, "signature": tablet.sign(screen_id, nonce)})
    assert r.status_code == 204, r.text
    assert "cave_screen=" in r.headers["set-cookie"] and "samesite=strict" in r.headers["set-cookie"].lower()
    return c


def test_screen_signs_in_and_uses_assigned_dashboard(app, users, garage):
    c = screen_client(app, "garage", approved_screen(app.state.db, "garage"))
    assert c.post(OPEN_GARAGE, json={}).status_code == 202
    assert garage.calls == [("cover.garage_door", "open", {})]


def test_screen_off_network_refused(app, users, garage):
    c = screen_client(app, "garage", approved_screen(app.state.db, "garage"), ip="203.0.113.9")
    assert c.post(OPEN_GARAGE, json={}).status_code == 403


def test_unenrolled_or_other_screen_refused(app, users, garage):
    c = screen_client(app, "other", approved_screen(app.state.db, "other"))
    assert c.post(OPEN_GARAGE, json={}).status_code == 403
    assert lan_client(app).post(OPEN_GARAGE, json={}).status_code == 401


def test_pending_screen_cannot_get_challenge(app, users):
    _, code = screens.create(app.state.db, "test", "Pending", T0, screen_id="pending")
    screens.enroll(app.state.db, code, FakeTablet().spki_b64, T0)
    r = lan_client(app).post("/api/v1/screen-auth/challenge", json={"screen_id": "pending"})
    assert r.status_code == 401


def test_replayed_signature_refused(app, users, garage):  # Review Focus 1
    tablet = approved_screen(app.state.db, "garage")
    c = lan_client(app)
    nonce = c.post("/api/v1/screen-auth/challenge", json={"screen_id": "garage"}).json()["nonce"]
    body = {"screen_id": "garage", "nonce": nonce, "signature": tablet.sign("garage", nonce)}
    assert c.post("/api/v1/screen-auth/verify", json=body).status_code == 204
    assert lan_client(app).post("/api/v1/screen-auth/verify", json=body).status_code == 401


def test_failed_attempt_also_consumes_nonce(app, users):
    tablet = approved_screen(app.state.db, "garage")
    c = lan_client(app)
    nonce = c.post("/api/v1/screen-auth/challenge", json={"screen_id": "garage"}).json()["nonce"]
    bad = {"screen_id": "garage", "nonce": nonce, "signature": FakeTablet().sign("garage", nonce)}
    assert c.post("/api/v1/screen-auth/verify", json=bad).status_code == 401
    good = {"screen_id": "garage", "nonce": nonce, "signature": tablet.sign("garage", nonce)}
    assert c.post("/api/v1/screen-auth/verify", json=good).status_code == 401


def test_signature_for_other_screen_refused(app, users):  # Review Focus 2
    a = approved_screen(app.state.db, "garage")
    b = approved_screen(app.state.db, "other")
    c = lan_client(app)
    nonce = c.post("/api/v1/screen-auth/challenge", json={"screen_id": "garage"}).json()["nonce"]
    # B's key, claiming to be A
    r = c.post("/api/v1/screen-auth/verify",
               json={"screen_id": "garage", "nonce": nonce, "signature": b.sign("garage", nonce)})
    assert r.status_code == 401
    # A's key, but a signature made for B's name, replayed as A
    nonce = c.post("/api/v1/screen-auth/challenge", json={"screen_id": "garage"}).json()["nonce"]
    r = c.post("/api/v1/screen-auth/verify",
               json={"screen_id": "garage", "nonce": nonce, "signature": a.sign("other", nonce)})
    assert r.status_code == 401
    # A's challenge presented for B
    nonce = c.post("/api/v1/screen-auth/challenge", json={"screen_id": "garage"}).json()["nonce"]
    r = c.post("/api/v1/screen-auth/verify",
               json={"screen_id": "other", "nonce": nonce, "signature": b.sign("other", nonce)})
    assert r.status_code == 401


def test_garbage_signature_refused(app, users):
    approved_screen(app.state.db, "garage")
    c = lan_client(app)
    nonce = c.post("/api/v1/screen-auth/challenge", json={"screen_id": "garage"}).json()["nonce"]
    for sig in ("", "not-base64!!", "AAAA"):
        nonce = c.post("/api/v1/screen-auth/challenge", json={"screen_id": "garage"}).json()["nonce"]
        r = c.post("/api/v1/screen-auth/verify", json={"screen_id": "garage", "nonce": nonce, "signature": sig})
        assert r.status_code in (401, 422)


def test_challenge_expires_after_60s(db):
    tablet = approved_screen(db, "garage")
    nonce = screens.issue_challenge(db, "garage", T0)
    with pytest.raises(screens.EnrollError):
        screens.verify_challenge(db, "garage", nonce, tablet.sign("garage", nonce), T0 + timedelta(seconds=61))


def test_screen_session_expires_after_12h(db):
    tablet = approved_screen(db, "garage")
    nonce = screens.issue_challenge(db, "garage", T0)
    sid = screens.verify_challenge(db, "garage", nonce, tablet.sign("garage", nonce), T0)
    assert screens.screen_from_session(db, sid, T0 + timedelta(hours=11, minutes=59)) is not None
    assert screens.screen_from_session(db, sid, T0 + timedelta(hours=12, seconds=1)) is None


def test_screen_cannot_reach_admin_or_me(app, users, garage):
    c = screen_client(app, "garage", approved_screen(app.state.db, "garage"))
    assert c.get("/api/v1/me").status_code == 401
    assert c.get("/api/v1/users").status_code in (401, 403)
    allowed = {i["id"] for i in c.get("/api/v1/items").json() if i["allowed"]}
    assert allowed == {"dashboard:garage"}


def test_revoked_screen_session_ends(app, users, garage):
    c = screen_client(app, "garage", approved_screen(app.state.db, "garage"))
    screens.revoke(app.state.db, "test", "garage")
    assert c.post(OPEN_GARAGE, json={}).status_code == 401
