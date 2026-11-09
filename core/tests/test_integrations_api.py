import asyncio
import json
import logging
import time

import pytest

from cave import audit
from cave.access import netconfig
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


@pytest.mark.parametrize("host", ["8.8.8.8", "127.0.0.1", "bridge.local", "192.168.1.40:80", "0.0.0.0", "224.0.0.1"])
def test_refuses_non_local_hosts(app, users, fake, host):
    netconfig.save(app.state.db, "test", ["192.168.1.0/24", "0.0.0.0/32", "224.0.0.0/4"], [])
    c = admin(app, users)
    for path in ("probe", "devices"):
        r = c.post(f"/api/v1/integrations/fake/{path}", json={"host": host})
        assert r.status_code == 422 and r.json()["detail"] == BAD
    assert not [x for x in fake.calls if x[0] in ("probe", "pair")]


def test_refuses_loopback_even_when_a_range_includes_it(app, users, fake):
    netconfig.save(app.state.db, "test", ["192.168.1.0/24", "127.0.0.0/8"], [])
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


def test_register_attaches_stored_devices_and_survives_one_failure(app, caplog):
    fake = FakeIntegration(domain="fake")
    for did in ("aaaaaaaaaaaa", "bbbbbbbbbbbb"):
        app.state.db.execute("INSERT INTO integration_devices (integration, device_id, host, model, name)"
                             " VALUES ('fake', ?, '192.168.1.40', 'm', 'n')", (did,))
    fake.attach_fails = {"aaaaaaaaaaaa"}
    app.state.integrations.register(fake)
    assert ("attach", "bbbbbbbbbbbb@192.168.1.40") in fake.calls
    assert "aaaaaaaaaaaa" in caplog.text


def test_attach_failure_during_add_still_returns_and_audits(app, users, fake, caplog):
    fake.attach_fails = {"aabbccddeeff"}
    r = add(admin(app, users))
    assert r.status_code == 201 and r.json()["device_id"] == "aabbccddeeff"
    assert audit.list_entries(app.state.db)[0]["action"] == "integration.add"
    assert "aabbccddeeff" in caplog.text and SECRET not in caplog.text


def test_one_crashing_run_does_not_stop_the_others(app, caplog):

    class Crash(FakeIntegration):
        async def run(self) -> None:
            raise RuntimeError("kaput")

    class Steady(FakeIntegration):
        ticks = 0

        async def run(self) -> None:
            while True:
                self.ticks += 1
                await asyncio.sleep(0.01)

    steady = Steady(domain="steady")
    app.state.integrations.register(Crash(domain="crash"))
    app.state.integrations.register(steady)
    async def main():
        task = asyncio.create_task(app.state.integrations.run())
        await asyncio.sleep(0.1)
        assert steady.ticks > 2 and not task.done()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(main())
    assert "crash integration stopped" in caplog.text


def test_register_attaches_rows_stored_first(app):
    app.state.db.execute("INSERT INTO integration_devices (integration, device_id, host, model, name)"
                         " VALUES ('late', 'cccccccccccc', '192.168.1.40', 'm', 'n')")
    late = FakeIntegration(domain="late")
    app.state.integrations.register(late)
    assert ("attach", "cccccccccccc@192.168.1.40") in late.calls


def test_probe_oserror_is_404(app, users, fake):
    fake.probe_error = OSError("refused http://x/?token=abc")
    r = admin(app, users).post("/api/v1/integrations/fake/probe", json={"host": "192.168.1.40"})
    assert r.status_code == 404 and r.json()["detail"] == "Nothing CAVE recognizes answered at that address."


def test_probe_failure_logs_type_only(app, users, fake, caplog):
    fake.probe_error = ValueError("secret-in-text")
    admin(app, users).post("/api/v1/integrations/fake/probe", json={"host": "192.168.1.40"})
    assert "ValueError" in caplog.text and "secret-in-text" not in caplog.text


def test_pair_timeout_is_422(app, users, fake, monkeypatch):
    monkeypatch.setattr(base, "PAIR_SECONDS", 0.05)
    fake.pair_delay = 1.0
    r = add(admin(app, users))
    assert r.status_code == 422
    assert r.json()["detail"] == "The device didn't answer. Check it's on and try again."


def test_pair_unexpected_error_is_422_without_text(app, users, fake, caplog):
    fake.pair_error = RuntimeError("secret-in-text")
    r = add(admin(app, users))
    assert r.status_code == 422 and r.json()["detail"] == "Pairing failed. Check the device and try again."
    assert "secret-in-text" not in caplog.text and "secret-in-text" not in r.text


def test_failing_detach_does_not_block_remove_or_readd(app, users, fake):
    c = admin(app, users)
    add(c)
    fake.detach_fails = True
    assert add(c, "192.168.1.42").status_code == 200
    assert ("attach", "aabbccddeeff@192.168.1.42") in fake.calls
    assert c.delete("/api/v1/integrations/fake/devices/aabbccddeeff").status_code == 204
    assert app.state.db.execute("SELECT 1 FROM integration_devices").fetchone() is None
    assert not app.state.credentials.is_set("fake", "aabbccddeeff:key")
    assert audit.list_entries(app.state.db)[0]["action"] == "integration.remove"


def test_overlong_secret_is_422_without_echo(app, users, fake):
    secret = "s3cr3t-" * 50
    r = add(admin(app, users), secret=secret)
    assert r.status_code == 422 and secret not in r.text
    assert r.json()["detail"] == "That's too long to be a device password or key."


def test_empty_secret_is_passed_as_none(app, users, fake):
    assert add(admin(app, users), secret="").status_code == 201
    assert fake.secrets == [None]


def test_device_id_with_colon_is_refused(app, users, fake):
    fake.answers["192.168.1.40"] = Found("aa:bb", "192.168.1.40", "Model X", "Lamp")
    r = add(admin(app, users))
    assert r.status_code == 422 and r.json()["detail"] == "This device reported an id CAVE can't use."
    assert app.state.db.execute("SELECT 1 FROM integration_devices").fetchone() is None
