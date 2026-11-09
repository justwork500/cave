import json
import logging
import time

import pytest

from cave import audit
from cave.integrations import base
from cave.integrations.base import Found, PairingError
from tests.conftest import lan_client, sign_in
from tests.fake_integration import FakeIntegration

BAD = "Use the device's address on your home network, like 192.168.1.40."
SECRET = "pair-secret-123"


def found(host="192.168.1.40"):
    return Found("aabbccddeeff", host, "Model X", "Lamp")


@pytest.fixture
def fake(app):
    f = FakeIntegration(domain="fake", pairing="key")
    f.answers = {"192.168.1.40": found(), "192.168.1.42": found("192.168.1.42")}
    app.state.integrations.register(f)
    return f


def admin(app, users):
    return sign_in(lan_client(app), "admin", "pw-admin-1234", users.admin_totp)


def add(c, host="192.168.1.40", secret=SECRET):
    return c.post("/api/v1/integrations/fake/devices", json={"host": host, "secret": secret})


def test_lists_integrations_with_devices(app, users, fake):
    c = admin(app, users)
    assert add(c).status_code == 201
    r = c.get("/api/v1/integrations")
    body = r.json()
    assert body[0]["domain"] == "fake" and body[0]["pairing"] == "key"
    assert body[0]["devices"][0]["device_id"] == "aabbccddeeff"
    assert "secret" not in r.text and SECRET not in r.text


def test_probe_found_and_not_found(app, users, fake):
    c = admin(app, users)
    r = c.post("/api/v1/integrations/fake/probe", json={"host": "192.168.1.40"})
    assert r.status_code == 200 and r.json()["added"] is False
    r = c.post("/api/v1/integrations/fake/probe", json={"host": "192.168.1.41"})
    assert r.status_code == 404 and r.json()["detail"] == "Nothing CAVE recognizes answered at that address."


def test_probe_times_out(app, users, fake, monkeypatch):
    monkeypatch.setattr(base, "PROBE_SECONDS", 0.05)
    fake.probe_delay = 1.0
    start = time.monotonic()
    r = admin(app, users).post("/api/v1/integrations/fake/probe", json={"host": "192.168.1.40"})
    assert r.status_code == 404 and time.monotonic() - start < 1.0


def test_add_stores_device_credential_and_audit(app, users, fake, caplog):
    caplog.set_level(logging.DEBUG)
    r = add(admin(app, users))
    assert r.status_code == 201
    assert app.state.credentials.get("fake", "aabbccddeeff:key") == SECRET
    entries = audit.list_entries(app.state.db)
    assert next(e for e in entries if e["action"].startswith("integration."))["action"] == "integration.add"
    assert SECRET not in json.dumps(entries) and SECRET not in r.text and SECRET not in caplog.text


def test_add_same_device_new_address_updates_host(app, users, fake):
    c = admin(app, users)
    add(c)
    r = add(c, "192.168.1.42")
    assert r.status_code == 200
    rows = app.state.db.execute("SELECT host FROM integration_devices").fetchall()
    assert [x["host"] for x in rows] == ["192.168.1.42"]
    update = next(e for e in audit.list_entries(app.state.db) if e["action"].startswith("integration."))
    assert update["action"] == "integration.update"
    assert update["old"] == {"host": "192.168.1.40"} and update["new"] == {"host": "192.168.1.42"}
    assert ("attach", "aabbccddeeff@192.168.1.42") in fake.calls


def test_pairing_error_is_422_with_message(app, users, fake):
    fake.pair_error = PairingError("Press the button on the bridge first.")
    r = add(admin(app, users))
    assert r.status_code == 422 and r.json()["detail"] == "Press the button on the bridge first."
    assert app.state.db.execute("SELECT 1 FROM integration_devices").fetchone() is None


@pytest.mark.parametrize("host", ["8.8.8.8", "127.0.0.1", "bridge.local", "192.168.1.40:80"])
def test_refuses_non_local_hosts(app, users, fake, host):
    c = admin(app, users)
    for path in ("probe", "devices"):
        r = c.post(f"/api/v1/integrations/fake/{path}", json={"host": host})
        assert r.status_code == 422 and r.json()["detail"] == BAD
    assert not [x for x in fake.calls if x[0] in ("probe", "pair")]


def test_refuses_loopback_even_when_a_range_includes_it(app, users, fake):
    app.state.settings.local_ranges.append("127.0.0.0/8")
    r = admin(app, users).post("/api/v1/integrations/fake/probe", json={"host": "127.0.0.1"})
    assert r.status_code == 422 and r.json()["detail"] == BAD


def test_unknown_integration_is_404(app, users, fake):
    r = admin(app, users).post("/api/v1/integrations/nope/probe", json={"host": "192.168.1.40"})
    assert r.status_code == 404 and r.json()["detail"] == "No such integration."


def test_remove_detaches_and_deletes_credentials(app, users, fake):
    c = admin(app, users)
    add(c)
    r = c.delete("/api/v1/integrations/fake/devices/aabbccddeeff")
    assert r.status_code == 204
    assert ("detach", "aabbccddeeff") in fake.calls
    assert not app.state.credentials.is_set("fake", "aabbccddeeff:key")
    assert audit.list_entries(app.state.db)[0]["action"] == "integration.remove"
    assert c.delete("/api/v1/integrations/fake/devices/aabbccddeeff").json()["detail"] == "No such device."


def test_needs_devices_section(app, users, fake):
    c = sign_in(lan_client(app), "sam", "pw-sam-1234")
    assert c.get("/api/v1/integrations").status_code == 403
    assert c.post("/api/v1/integrations/fake/probe", json={"host": "192.168.1.40"}).status_code == 403
    assert add(c).status_code == 403
    assert c.delete("/api/v1/integrations/fake/devices/aabbccddeeff").status_code == 403


def test_load_attaches_stored_devices_and_survives_one_failure(app, fake, caplog):
    for did in ("aaaaaaaaaaaa", "bbbbbbbbbbbb"):
        app.state.db.execute("INSERT INTO integration_devices (integration, device_id, host, model, name)"
                             " VALUES ('fake', ?, '192.168.1.40', 'm', 'n')", (did,))
    fake.attach_fails = {"aaaaaaaaaaaa"}
    app.state.integrations.load()
    assert ("attach", "bbbbbbbbbbbb@192.168.1.40") in fake.calls
    assert "aaaaaaaaaaaa" in caplog.text
