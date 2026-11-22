import asyncio
import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest

from cave.credentials import Credentials
from cave.db import Database
from cave.integrations.base import Device, PairingError
from cave.integrations.fully.service import FullyKioskIntegration
from cave.integrations.http import NOT_RESPONDING
from cave.state import EventBus, StateMachine
from tests.fake_http import FakeHttp

FIX = Path(__file__).parent / "fixtures" / "fully"
HOST = "192.168.1.80"
TID = "a1b2c3d4"
PW = "s3cret pw&x=1"
Q = f"/?cmd=deviceInfo&type=json&password={quote(PW, safe='')}"
INFO = "/?cmd=deviceInfo&type=json"
SCREEN, BRIGHT, BATT = f"switch.fully_{TID}_screen", f"number.fully_{TID}_brightness", f"sensor.fully_{TID}_battery"
ALL = [SCREEN, BRIGHT, BATT]


def fixture(name: str) -> Any:
    return json.loads((FIX / f"{name}.json").read_text())


def make(db: Database) -> tuple[FullyKioskIntegration, StateMachine, FakeHttp]:
    creds = Credentials(db, bytes(range(32)))
    creds.set("fully", f"{TID}:password", PW, "test")
    fake = FakeHttp({("GET", Q): fixture("device_info"), ("GET", INFO): fixture("login_needed")})
    states = StateMachine(EventBus())
    fully = FullyKioskIntegration(states, creds, fake)
    fully.attach(Device("fully", TID, HOST, "Lenovo Tab M10", "Hall tablet", {}))
    return fully, states, fake


def value(states: StateMachine, entity: str) -> Any:
    s = states.get(entity)
    assert s
    return s


def test_probe_sees_fully_before_the_password(db: Database) -> None:
    fully, _, fake = make(db)
    found = asyncio.run(fully.probe(HOST))
    assert found and (found.device_id, found.host, found.model, found.name) == ("", HOST, "Fully Kiosk Browser", "Fully Kiosk Browser")
    fake.routes[("GET", INFO)] = fixture("device_info")  # no password set
    found = asyncio.run(fully.probe(HOST))
    assert found and (found.device_id, found.model, found.name) == (TID, "Lenovo Tab M10", "Hall tablet")
    fake.routes[("GET", INFO)] = {"hello": "world"}
    assert asyncio.run(fully.probe(HOST)) is None
    fake.routes[("GET", INFO)] = "<html>"
    assert asyncio.run(fully.probe(HOST)) is None


def test_pair_checks_the_password(db: Database) -> None:
    fully, _, fake = make(db)
    bad = f"{INFO}&password=nope"
    fake.routes[("GET", bad)] = fixture("login_needed")
    with pytest.raises(PairingError) as e:
        asyncio.run(fully.pair(HOST, "nope"))
    assert str(e.value) == "That password didn't work. Check Remote Administration in Fully Kiosk's settings."
    found, creds = asyncio.run(fully.pair(HOST, PW))  # the awkward characters are encoded
    assert found.device_id == TID and creds == {"password": PW}
    fake.routes[("GET", Q)] = {**fixture("device_info"), "deviceID": "--"}
    with pytest.raises(PairingError, match="didn't report an id"):
        asyncio.run(fully.pair(HOST, PW))
    fake.routes[("GET", Q)] = "<html>"
    with pytest.raises(PairingError):
        asyncio.run(fully.pair(HOST, PW))


def test_poll_and_commands(db: Database) -> None:
    fully, states, fake = make(db)
    assert all(value(states, e).value == "unavailable" for e in ALL)
    asyncio.run(fully.poll())
    assert value(states, SCREEN).value == "on"
    b = value(states, BRIGHT)
    assert (b.value, b.attributes["min"], b.attributes["max"], b.attributes["step"]) == ("120", 0, 255, 1)
    s = value(states, BATT)
    assert (s.value, s.attributes["unit"]) == ("87", "%")
    def base(cmd: str) -> str:
        return f"/?cmd={cmd}&password={quote(PW, safe='')}"

    fake.routes[("GET", base("screenOff"))] = {"status": "OK"}
    fake.routes[("GET", base("setStringSetting&key=screenBrightness&value=200"))] = {"status": "OK"}
    asyncio.run(states.command(BRIGHT, "set_value", {"value": 200}))
    assert fake.calls[-1][2] == base("setStringSetting&key=screenBrightness&value=200")
    assert value(states, BRIGHT).value == "200"
    asyncio.run(states.command(SCREEN, "turn_off", {}))
    assert fake.calls[-1][2] == base("screenOff") and value(states, SCREEN).value == "off"
    fake.routes[("GET", base("screenOff"))] = fixture("login_needed")
    with pytest.raises(ValueError, match="refused"):
        asyncio.run(states.command(SCREEN, "turn_off", {}))


def test_password_never_logged(db: Database, caplog: pytest.LogCaptureFixture) -> None:
    fully, states, fake = make(db)
    caplog.set_level(logging.DEBUG)
    fake.offline = True
    asyncio.run(fully.poll())
    with pytest.raises(ValueError) as e:
        asyncio.run(states.command(SCREEN, "turn_on", {}))
    for secret in (PW, quote(PW, safe="")):
        assert secret not in caplog.text and secret not in str(e.value)
    assert str(e.value) == NOT_RESPONDING and value(states, SCREEN).value == "unavailable"


def test_unreadable_password_reads_unavailable(db: Database, caplog: pytest.LogCaptureFixture) -> None:
    fully, states, fake = make(db)
    asyncio.run(fully.poll())
    fully.credentials = Credentials(db, bytes(32))  # a replaced host key
    calls = len(fake.calls)
    asyncio.run(fully.poll())
    assert all(value(states, e).value == "unavailable" for e in ALL)
    assert len(fake.calls) == calls
    assert TID in caplog.text and "add it again" in caplog.text and PW not in caplog.text
    with pytest.raises(ValueError, match=NOT_RESPONDING):
        asyncio.run(states.command(SCREEN, "turn_on", {}))


def test_odd_reply_and_detach(db: Database) -> None:
    fully, states, fake = make(db)
    fake.routes[("GET", Q)] = fixture("login_needed")  # password changed on the tablet
    asyncio.run(fully.poll())
    assert all(value(states, e).value == "unavailable" for e in ALL)
    fake.routes[("GET", Q)] = fixture("device_info")
    asyncio.run(fully.poll())
    assert value(states, SCREEN).value == "on"
    fully.detach(TID)
    assert all(states.entity(e) is None for e in ALL)
    asyncio.run(fully._poll_one(TID))
