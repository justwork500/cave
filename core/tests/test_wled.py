import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from cave.integrations.base import Device, Found, PairingError
from cave.integrations.http import NOT_RESPONDING
from cave.integrations.wled.service import WledIntegration
from cave.state import EventBus, StateMachine
from tests.fake_http import FakeHttp

FIX = Path(__file__).parent / "fixtures" / "wled"
MAC, HOST = "aabbccddeeff", "192.168.1.50"
LIGHT, PRESET = f"light.wled_{MAC}", f"select.wled_{MAC}_preset"


def fixture(name: str) -> Any:
    return json.loads((FIX / f"{name}.json").read_text())


def make() -> tuple[WledIntegration, StateMachine, FakeHttp]:
    fake = FakeHttp({("GET", "/json/info"): fixture("info"), ("GET", "/json/state"): fixture("state"),
                     ("GET", "/presets.json"): fixture("presets"), ("POST", "/json/state"): {"success": True}})
    states = StateMachine(EventBus())
    wled = WledIntegration(states, None, fake)  # type: ignore[arg-type]  # WLED stores no credentials
    wled.attach(Device("wled", MAC, HOST, "esp32", "Desk strip", {}))
    return wled, states, fake


def posts(fake: FakeHttp) -> list[Any]:
    return [c[3] for c in fake.calls if c[0] == "POST"]


def test_probe_recognises_wled_only() -> None:
    wled, _, fake = make()
    assert asyncio.run(wled.probe(HOST)) == Found(MAC, HOST, "esp32", "Desk strip")
    fake.routes[("GET", "/json/info")] = {"name": "x", "mac": "aa", "arch": "esp32"}
    assert asyncio.run(wled.probe(HOST)) is None
    with pytest.raises(PairingError):
        asyncio.run(wled.pair(HOST, None))


def test_poll_sets_light_and_preset() -> None:
    wled, states, _ = make()
    asyncio.run(wled.poll())
    light, preset = states.get(LIGHT), states.get(PRESET)
    assert light and light.value == "on" and light.attributes["brightness"] == 128
    assert preset and preset.value == "Warm white" and preset.attributes["options"] == ["Warm white", "Sunset"]


def test_commands_post_state() -> None:
    wled, states, fake = make()
    asyncio.run(wled.poll())
    asyncio.run(states.command(LIGHT, "turn_on", {"brightness": 200}))
    asyncio.run(states.command(PRESET, "select_option", {"option": "Sunset"}))
    assert posts(fake) == [{"on": True, "bri": 200}, {"ps": 2}]
    with pytest.raises(ValueError):
        asyncio.run(states.command(PRESET, "select_option", {"option": "Nope"}))
    assert len(posts(fake)) == 2
    asyncio.run(states.command(LIGHT, "toggle", {}))
    assert posts(fake)[-1] == {"on": False}


def test_offline_reads_unavailable_and_commands_say_so() -> None:
    wled, states, fake = make()
    asyncio.run(wled.poll())
    fake.offline = True
    asyncio.run(wled.poll())
    for e in (LIGHT, PRESET):
        s = states.get(e)
        assert s and s.value == "unavailable"
    with pytest.raises(ValueError, match=NOT_RESPONDING):
        asyncio.run(states.command(LIGHT, "turn_off", {}))


def test_renamed_preset_shows_on_next_poll() -> None:
    wled, states, fake = make()
    asyncio.run(wled.poll())
    fake.routes[("GET", "/presets.json")] = {"0": {}, "1": {"n": "Cosy"}, "2": {"n": "Sunset"}}
    asyncio.run(wled.poll())
    preset = states.get(PRESET)
    assert preset and preset.value == "Cosy" and preset.attributes["options"] == ["Cosy", "Sunset"]


def test_detach_removes_entities() -> None:
    wled, states, _ = make()
    wled.detach(MAC)
    wled.detach("unknown")
    assert states.entity(LIGHT) is None and states.entity(PRESET) is None
