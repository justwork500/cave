import hashlib
from datetime import timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from cave.auth import screens
from tests.conftest import T0, sign_in
from tests.screen_key import FakeTablet, spki_b64_of


def as_admin(client, users):
    return sign_in(client, "admin", "pw-admin-1234", users.admin_totp)


def code_from(url: str) -> str:
    return url.split("#", 1)[1]


def test_enroll_then_pending_then_approved(client, users):
    as_admin(client, users)
    r = client.post("/api/v1/screens", json={"name": "Garage tablet"})
    assert r.status_code == 201
    body = r.json()
    assert body["screen"]["status"] == "awaiting_key" and body["enroll_url"].startswith("https://testserver/enroll#")
    tablet = FakeTablet()
    r = client.post("/api/v1/enroll", json={"code": code_from(body["enroll_url"]), "public_key": tablet.spki_b64})
    assert r.status_code == 200 and r.json()["status"] == "pending"
    sid = body["screen"]["id"]
    assert client.post(f"/api/v1/screens/{sid}/approve").json()["status"] == "approved"
    actions = [e["action"] for e in client.get("/api/v1/audit").json()]
    assert {"screen.create", "screen.enroll", "screen.approve"} <= set(actions)


def test_code_single_use(db):  # Review Focus 3
    _, code = screens.create(db, "user:a", "Tablet", T0)
    screens.enroll(db, code, FakeTablet().spki_b64, T0)
    with pytest.raises(screens.EnrollError, match="expired"):
        screens.enroll(db, code, FakeTablet().spki_b64, T0)


def test_code_expires_after_10_minutes(db):  # Review Focus 3
    s, code = screens.create(db, "user:a", "Tablet", T0)
    with pytest.raises(screens.EnrollError, match="expired"):
        screens.enroll(db, code, FakeTablet().spki_b64, T0 + timedelta(minutes=10, seconds=1))
    got = screens.get_screen(db, s.id)
    assert got is not None and got.status == "awaiting_key" and got.fingerprint is None


def test_unknown_code_refused(db):
    with pytest.raises(screens.EnrollError):
        screens.enroll(db, "made-up", FakeTablet().spki_b64, T0)


@pytest.mark.parametrize(
    "key",
    [
        rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key(),
        ec.generate_private_key(ec.SECP384R1()).public_key(),
    ],
)
def test_rejects_non_p256_key(client, users, key):
    as_admin(client, users)
    url = client.post("/api/v1/screens", json={"name": "T"}).json()["enroll_url"]
    r = client.post("/api/v1/enroll", json={"code": code_from(url), "public_key": spki_b64_of(key)})
    assert r.status_code == 400 and r.json() == {"detail": "This browser's key isn't supported."}


def test_garbage_key_refused(db):
    _, code = screens.create(db, "user:a", "Tablet", T0)
    with pytest.raises(screens.EnrollError, match="supported"):
        screens.enroll(db, code, "not base64 at all!!", T0)


def test_fingerprint_matches_spki_sha256(db):
    _, code = screens.create(db, "user:a", "Tablet", T0)
    tablet = FakeTablet()
    s = screens.enroll(db, code, tablet.spki_b64, T0)
    h = hashlib.sha256(tablet.spki_der).hexdigest().upper()
    assert s.fingerprint == ":".join(h[i : i + 2] for i in range(0, 64, 2))


def test_only_admin_creates_screens(client, users):
    sign_in(client, "op", "pw-op-1234", users.op_totp)
    assert client.post("/api/v1/screens", json={"name": "T"}).status_code == 403
    assert client.get("/api/v1/screens").status_code == 403


def test_approve_requires_pending(client, users):
    as_admin(client, users)
    sid = client.post("/api/v1/screens", json={"name": "T"}).json()["screen"]["id"]
    assert client.post(f"/api/v1/screens/{sid}/approve").status_code == 409


def test_revoke_clears_key(db):
    s, code = screens.create(db, "user:a", "Tablet", T0)
    screens.enroll(db, code, FakeTablet().spki_b64, T0)
    screens.revoke(db, "user:a", s.id)
    assert screens.get_screen(db, s.id).status == "revoked"
    assert db.execute("SELECT public_key FROM screens WHERE id=?", (s.id,)).fetchone()[0] is None


def test_enroll_page_reads_code_from_fragment(client):
    r = client.get("/enroll")
    assert r.status_code == 200 and 'src="/static/enroll.js"' in r.text
    assert "location.hash" in client.get("/static/enroll.js").text
