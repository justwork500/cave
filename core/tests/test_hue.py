import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import pytest

from cave.credentials import Credentials
from cave.db import Database
from cave.integrations.base import Device, PairingError
from cave.integrations.http import NOT_RESPONDING, DeviceError
from cave.integrations.hue.service import HueIntegration
from cave.state import EventBus, StateMachine
from tests.fake_http import FakeHttp

FIX = Path(__file__).parent / "fixtures" / "hue"
HOST = "192.168.1.70"
BID = "001788fffe123456"
KEY = "sekrit-key-123"
SETTINGS = {"lights": {"1": "Hall light", "2": "Desk lamp"}, "motion": {"3": "Hall motion"}, "temperature": {"4": "Hall temperature"}}
ALL = [f"light.hue_{BID}_1", f"light.hue_{BID}_2", f"binary_sensor.hue_{BID}_3_motion", f"sensor.hue_{BID}_4_temperature"]


def fixture(name: str) -> Any:
    return json.loads((FIX / f"{name}.json").read_text())


def routes() -> dict[tuple[str, str], Any]:
    return {("GET", "/api/config"): fixture("config"), ("GET", f"/api/{KEY}/lights"): fixture("lights"),
            ("GET", f"/api/{KEY}/sensors"): fixture("sensors")}


def make(db: Database, settings: dict[str, Any] | None = SETTINGS) -> tuple[HueIntegration, StateMachine, FakeHttp]:
    creds = Credentials(db, bytes(range(32)))
    creds.set("hue", f"{BID}:key", KEY, "test")
    fake = FakeHttp(routes())
    states = StateMachine(EventBus())
    hue = HueIntegration(states, creds, fake)
    hue.attach(Device("hue", BID, HOST, "BSB002", "Bridge", settings or {}))
    return hue, states, fake


def value(states: StateMachine, entity: str) -> Any:
    s = states.get(entity)
    assert s
    return s


def test_probe_and_pair(db: Database) -> None:
    hue, _, fake = make(db)
    found = asyncio.run(hue.probe(HOST))
    assert found and (found.device_id, found.model, found.name) == (BID, "BSB002", "Hue Bridge")
    fake.routes[("POST", "/api")] = [{"error": {"type": 101, "description": "link button not pressed"}}]
    with pytest.raises(PairingError) as e:
        asyncio.run(hue.pair(HOST, None))
    assert str(e.value) == "Press the button on the Hue bridge first, then choose Add again."
    fake.routes[("POST", "/api")] = [{"success": {"username": KEY}}]
    found, creds = asyncio.run(hue.pair(HOST, None))
    assert creds == {"key": KEY} and found.settings == SETTINGS
    assert ("POST", HOST, "/api", {"devicetype": "cave#hub"}) in fake.calls
    fake.routes[("GET", "/api/config")] = {"hello": "world"}
    assert asyncio.run(hue.probe(HOST)) is None


def test_poll_lights_and_sensors(db: Database) -> None:
    hue, states, _ = make(db)
    asyncio.run(hue.poll())
    on = value(states, ALL[0])
    assert (on.value, on.attributes["brightness"]) == ("on", 128)  # 127 of 254
    assert value(states, ALL[1]).value == "unavailable"  # reachable: false
    assert value(states, ALL[2]).value == "on"
    t = value(states, ALL[3])
    assert (t.value, t.attributes["unit"]) == ("21.5", "°C")
    assert sorted(e.entity_id for e in states.entities()) == sorted(ALL)  # nothing for Daylight


def test_new_and_missing_lights_follow_the_bridge(db: Database) -> None:
    hue, states, fake = make(db)
    asyncio.run(hue.poll())
    lights = fixture("lights")
    lights["3"] = {"name": "New", "state": {"on": True, "bri": 254, "reachable": True}}
    fake.routes[("GET", f"/api/{KEY}/lights")] = lights
    asyncio.run(hue.poll())
    assert value(states, f"light.hue_{BID}_3").attributes["brightness"] == 255
    del lights["1"]
    asyncio.run(hue.poll())
    assert value(states, ALL[0]).value == "unavailable"


def test_brightness_command_scales(db: Database) -> None:
    hue, states, fake = make(db)
    asyncio.run(hue.poll())
    fake.routes[("PUT", f"/api/{KEY}/lights/2/state")] = [{"success": {}}]
    asyncio.run(states.command(ALL[1], "turn_on", {"brightness": 255}))
    assert fake.calls[-1][2:] == (f"/api/{KEY}/lights/2/state", {"on": True, "bri": 254})
    assert value(states, ALL[1]).value == "on"
    asyncio.run(states.command(ALL[1], "toggle", {}))
    assert fake.calls[-1][3] == {"on": False}
    fake.routes[("PUT", f"/api/{KEY}/lights/2/state")] = [{"error": {"type": 201}}]
    with pytest.raises(ValueError):
        asyncio.run(states.command(ALL[1], "turn_off", {}))


def test_unreadable_key_reads_unavailable(db: Database, caplog: pytest.LogCaptureFixture) -> None:
    hue, states, fake = make(db)
    hue.credentials = Credentials(db, bytes(32))  # a replaced host key
    calls = len(fake.calls)
    asyncio.run(hue.poll())
    assert all(value(states, e).value == "unavailable" for e in ALL)
    assert len(fake.calls) == calls
    assert BID in caplog.text and "add it again" in caplog.text and KEY not in caplog.text


def test_offline_start_registers_unavailable(db: Database) -> None:
    hue, states, fake = make(db)
    fake.offline = True
    assert all(value(states, e).value == "unavailable" for e in ALL)
    asyncio.run(hue.poll())
    assert all(value(states, e).value == "unavailable" for e in ALL)
    with pytest.raises(ValueError, match=NOT_RESPONDING):
        asyncio.run(states.command(ALL[0], "turn_on", {}))
    fake.offline = False
    asyncio.run(hue.poll())
    assert value(states, ALL[0]).value == "on"
    hue.detach(BID)
    assert all(states.entity(e) is None for e in ALL)
    asyncio.run(hue._poll_one(BID))  # detached after poll() listed it


def test_key_never_logged(db: Database, caplog: pytest.LogCaptureFixture) -> None:
    hue, states, _ = make(db)
    caplog.set_level(logging.DEBUG)

    async def broken(method: str, host: str, path: str, **kw: Any) -> Any:
        raise DeviceError("HTTP 500")

    hue.fetch = broken
    asyncio.run(hue.poll())
    with pytest.raises(ValueError) as e:
        asyncio.run(states.command(ALL[0], "turn_on", {}))
    assert KEY not in caplog.text and KEY not in str(e.value)
    assert value(states, ALL[0]).value == "unavailable"


def test_pairing_names_survive_attach_and_old_shape_falls_back(db: Database) -> None:
    _, states, _ = make(db)
    entity = states.entity(ALL[0])
    assert entity and entity.name == "Hall light"
    entity = states.entity(ALL[2])
    assert entity and entity.name == "Hall motion"
    _, states2, _ = make(db, {"lights": ["1"]})  # an older save: ids without names
    entity = states2.entity(ALL[0])
    assert entity and entity.name == "Bridge light 1"
