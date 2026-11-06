"""Finding, adding and controlling Kasa devices. Fakes stand in for the network; nothing here touches a real device."""

import asyncio
import base64
import json

import pytest

from cave.integrations.kasa.discovery import Found, hosts_in, parse_reply
from cave.integrations.kasa.klap import KasaAuthError, KasaError
from tests.conftest import lan_client, sign_in

PLUG = Found("aabbccddee01", "192.168.1.50", "HS103(US)", "iot")
DIMMER = Found("aabbccddee02", "192.168.1.51", "KS225(US)", "smart")


class FakeDevice:
    """What a plug answers, for both of the message formats."""

    def __init__(self):
        self.on = False
        self.fail: Exception | None = None

    def request(self, payload):
        if self.fail:
            raise self.fail
        if "system" in payload:
            if "set_relay_state" in payload["system"]:
                self.on = bool(payload["system"]["set_relay_state"]["state"])
                return {"system": {"set_relay_state": {"err_code": 0}}}
            return {"system": {"get_sysinfo": {"relay_state": int(self.on), "alias": "Lamp"}}}
        if payload["method"] == "set_device_info":
            self.on = payload["params"]["device_on"]
            return {"error_code": 0}
        name = base64.b64encode(b"Hall").decode()
        return {"error_code": 0, "result": {"device_on": self.on, "nickname": name}}


@pytest.fixture
def device(app):
    d = FakeDevice()
    app.state.kasa.client = lambda host, hashes: d
    app.state.kasa.discover = lambda hosts: [PLUG, DIMMER]
    return d


@pytest.fixture
def admin(app, users):
    return sign_in(lan_client(app), "admin", "pw-admin-1234", users.admin_totp)


def login(c):
    assert c.put("/api/v1/kasa/login", json={"username": "sam@example.com", "password": "pw"}).status_code == 204


def test_scan_before_sign_in_finds_devices_and_asks_for_it(admin, device):
    out = admin.post("/api/v1/kasa/scan").json()
    assert out["signed_in"] is False and out["login_ok"] is None
    assert [d["model"] for d in out["devices"]] == ["HS103(US)", "KS225(US)"]
    assert out["devices"][0]["name"] is None


def test_add_a_plug_then_control_it(app, admin, device):
    login(admin)
    out = admin.post("/api/v1/kasa/scan").json()
    assert out["login_ok"] is True
    assert [d["name"] for d in out["devices"]] == ["Lamp", "Hall"]
    assert admin.post("/api/v1/kasa/devices", json={"mac": PLUG.mac}).status_code == 201
    entity = f"switch.kasa_{PLUG.mac}"
    assert app.state.states.entity(entity).name == "Lamp"
    assert app.state.states.get(entity).value == "off"
    assert admin.post(f"/api/v1/entities/{entity}/commands/toggle").status_code == 202
    assert device.on is True and app.state.states.get(entity).value == "on"


def test_the_smart_format_works_too(app, admin, device):
    login(admin)
    admin.post("/api/v1/kasa/scan")
    admin.post("/api/v1/kasa/devices", json={"mac": DIMMER.mac})
    entity = f"switch.kasa_{DIMMER.mac}"
    assert app.state.states.entity(entity).name == "Hall"
    admin.post(f"/api/v1/entities/{entity}/commands/turn_on")
    assert device.on is True


def test_a_wrong_sign_in_says_so(admin, device):
    login(admin)
    device.fail = KasaAuthError("no")
    out = admin.post("/api/v1/kasa/scan").json()
    assert out["login_ok"] is False
    r = admin.post("/api/v1/kasa/devices", json={"mac": PLUG.mac})
    assert r.status_code == 409 and "TP-Link" in r.json()["detail"]


def test_only_a_device_the_scan_found_can_be_added(admin, device):
    login(admin)
    assert admin.post("/api/v1/kasa/devices", json={"mac": PLUG.mac}).status_code == 404


def test_devices_survive_a_restart_and_can_be_removed(app, admin, device):
    login(admin)
    admin.post("/api/v1/kasa/scan")
    admin.post("/api/v1/kasa/devices", json={"mac": PLUG.mac})
    entity = f"switch.kasa_{PLUG.mac}"
    app.state.states.remove(entity)
    app.state.kasa.load()
    assert app.state.states.entity(entity) is not None
    assert admin.delete(f"/api/v1/kasa/devices/{PLUG.mac}").status_code == 204
    assert app.state.states.entity(entity) is None
    assert admin.post("/api/v1/kasa/scan").json()["devices"][0]["added"] is False


def test_a_plug_that_stops_answering_reads_unavailable_and_commands_say_why(app, admin, device):
    login(admin)
    admin.post("/api/v1/kasa/scan")
    admin.post("/api/v1/kasa/devices", json={"mac": PLUG.mac})
    entity = f"switch.kasa_{PLUG.mac}"
    device.fail = KasaError("gone")
    asyncio.run(app.state.kasa.poll())
    assert app.state.states.get(entity).value == "unavailable"
    r = admin.post(f"/api/v1/entities/{entity}/commands/turn_on")
    assert r.status_code == 409 and "responding" in r.json()["detail"]


def test_a_new_address_from_a_scan_is_remembered(app, admin, device):
    login(admin)
    admin.post("/api/v1/kasa/scan")
    admin.post("/api/v1/kasa/devices", json={"mac": PLUG.mac})
    app.state.kasa.discover = lambda hosts: [Found(PLUG.mac, "192.168.1.99", PLUG.model, PLUG.kind)]
    out = admin.post("/api/v1/kasa/scan").json()
    assert [(d["host"], d["added"]) for d in out["devices"]] == [("192.168.1.99", True)]


def test_devices_section_is_required(app, users, device):
    sam = sign_in(lan_client(app), "sam", "pw-sam-1234", users.sam_totp) if hasattr(users, "sam_totp") \
        else sign_in(lan_client(app), "sam", "pw-sam-1234")
    assert sam.post("/api/v1/kasa/scan").status_code == 403
    assert sam.put("/api/v1/kasa/login", json={"username": "a", "password": "b"}).status_code == 403


def test_the_password_is_never_stored_or_audited(app, admin, device):
    assert admin.put("/api/v1/kasa/login", json={"username": "sam@example.com",
                                                 "password": "hunter2-secret"}).status_code == 204
    rows = app.state.db.execute("SELECT old, new FROM audit WHERE action='kasa.login'").fetchall()
    assert len(rows) == 1
    assert "hunter2" not in json.dumps([dict(r) for r in rows]) and "sam@example.com" not in rows[0]["new"]


def test_replies_from_the_lan_are_checked():
    good = {"result": {"mac": "AA-BB-CC-DD-EE-01", "device_model": "HS103(US)", "device_type": "IOT.SMARTPLUGSWITCH",
                       "mgt_encrypt_schm": {"encrypt_type": "KLAP"}}}
    head = bytes(16)
    assert parse_reply(head + json.dumps(good).encode(), "10.0.0.5") == Found(
        "aabbccddee01", "10.0.0.5", "HS103(US)", "iot")
    bad_mac = json.loads(json.dumps(good))
    bad_mac["result"]["mac"] = "../../etc"
    assert parse_reply(head + json.dumps(bad_mac).encode(), "10.0.0.5") is None
    other = json.loads(json.dumps(good))
    other["result"]["mgt_encrypt_schm"]["encrypt_type"] = "AES"
    assert parse_reply(head + json.dumps(other).encode(), "10.0.0.5") is None
    assert parse_reply(b"junk", "10.0.0.5") is None


def test_scan_stays_inside_small_ipv4_ranges():
    assert len(hosts_in(["192.168.1.0/24"])) == 254
    assert hosts_in(["10.0.0.0/8", "fd00::/64", "127.0.0.0/30"]) == []
