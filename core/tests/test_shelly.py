import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from cave.integrations.base import Device, Found, PairingError
from cave.integrations.http import NOT_RESPONDING
from cave.integrations.shelly.service import ShellyIntegration
from cave.state import EventBus, StateMachine
from tests.fake_http import FakeHttp

FIX = Path(__file__).parent / "fixtures" / "shelly"
HOST = "192.168.1.60"
G1, G2 = "aabbccddeeff", "112233445566"


def fixture(name: str) -> Any:
    return json.loads((FIX / f"{name}.json").read_text())


def make(gen: int) -> tuple[ShellyIntegration, StateMachine, FakeHttp]:
    status = "/status" if gen == 1 else "/rpc/Shelly.GetStatus"
    fake = FakeHttp({("GET", "/shelly"): fixture(f"gen{gen}_shelly"), ("GET", status): fixture(f"gen{gen}_status")})
    states = StateMachine(EventBus())
    shelly = ShellyIntegration(states, None, fake)  # type: ignore[arg-type]  # Shelly stores no credentials
    mac = G1 if gen == 1 else G2
    shelly.attach(Device("shelly", mac, HOST, "x", "Relay", {}))
    return shelly, states, fake


def value(states: StateMachine, entity: str) -> Any:
    s = states.get(entity)
    assert s
    return s


def test_probe_both_generations() -> None:
    s1, _, f1 = make(1)
    s2, _, _ = make(2)
    assert asyncio.run(s1.probe(HOST)) == Found(G1, HOST, "SHSW-PM", "SHSW-PM")
    assert asyncio.run(s2.probe(HOST)) == Found(G2, HOST, "SNSW-102P16EU", "Hall switch")
    f1.routes[("GET", "/shelly")] = {"hello": "world"}
    assert asyncio.run(s1.probe(HOST)) is None


def test_pair_refuses_password_and_dimmers() -> None:
    s1, _, f1 = make(1)
    s2, _, f2 = make(2)
    found, creds = asyncio.run(s1.pair(HOST, None))
    assert found.device_id == G1 and creds == {} and found.settings == {"gen": 1, "channels": 1}
    assert asyncio.run(s2.pair(HOST, None))[0].settings == {"gen": 2, "channels": 2}
    f1.routes[("GET", "/shelly")] = {**fixture("gen1_shelly"), "auth": True}
    f2.routes[("GET", "/shelly")] = {**fixture("gen2_shelly"), "auth_en": True}
    for s in (s1, s2):
        with pytest.raises(PairingError) as e:
            asyncio.run(s.pair(HOST, None))
        assert str(e.value) == "This Shelly has a password set. CAVE can't use password-protected Shelly devices yet."
    f1.routes[("GET", "/shelly")] = fixture("gen1_shelly")
    f1.routes[("GET", "/status")] = {"lights": [{"ison": True}]}
    with pytest.raises(PairingError) as e:
        asyncio.run(s1.pair(HOST, None))
    assert str(e.value) == "CAVE supports Shelly relays for now, not dimmers or colour lights."


def test_gen1_poll_and_command() -> None:
    shelly, states, fake = make(1)
    fake.routes[("GET", "/relay/0?turn=off")] = {}
    asyncio.run(shelly.poll())
    assert value(states, f"switch.shelly_{G1}_0").value == "on"
    power, energy = value(states, f"sensor.shelly_{G1}_0_power"), value(states, f"sensor.shelly_{G1}_0_energy")
    assert (power.value, power.attributes["unit"]) == ("12.5", "W")
    assert (energy.value, energy.attributes["unit"]) == ("1.5", "kWh")
    asyncio.run(states.command(f"switch.shelly_{G1}_0", "turn_off", {}))
    assert fake.calls[-1][2] == "/relay/0?turn=off"
    assert value(states, f"switch.shelly_{G1}_0").value == "off"


def test_gen2_two_channels() -> None:
    shelly, states, fake = make(2)
    fake.routes[("GET", "/rpc/Switch.Toggle?id=1")] = {}
    asyncio.run(shelly.poll())
    assert [c[2] for c in fake.calls].count("/rpc/Shelly.GetStatus") == 1
    assert value(states, f"switch.shelly_{G2}_0").value == "on"
    assert value(states, f"switch.shelly_{G2}_1").value == "off"
    assert value(states, f"sensor.shelly_{G2}_0_power").value == "40.2"
    assert value(states, f"sensor.shelly_{G2}_0_energy").value == "1.5"  # 1500.5 Wh -> 1.5 kWh (3 places: 1.5)
    assert value(states, f"sensor.shelly_{G2}_1_energy").value == "0.02"
    asyncio.run(states.command(f"switch.shelly_{G2}_1", "toggle", {}))
    assert fake.calls[-1][2] == "/rpc/Switch.Toggle?id=1"
    assert value(states, f"switch.shelly_{G2}_1").value == "on"
    fake.routes[("GET", "/rpc/Switch.Set?id=0&on=false")] = {}
    asyncio.run(states.command(f"switch.shelly_{G2}_0", "turn_off", {}))
    assert fake.calls[-1][2] == "/rpc/Switch.Set?id=0&on=false"


def test_unexpected_reply_reads_unavailable() -> None:
    shelly, states, fake = make(2)
    asyncio.run(shelly.poll())
    status = fixture("gen2_status")
    del status["switch:0"]
    fake.routes[("GET", "/rpc/Shelly.GetStatus")] = status
    asyncio.run(shelly.poll())
    for e in (f"switch.shelly_{G2}_0", f"sensor.shelly_{G2}_0_power", f"sensor.shelly_{G2}_0_energy"):
        assert value(states, e).value == "unavailable"
    assert value(states, f"switch.shelly_{G2}_1").value == "off"
    fake.routes[("GET", "/rpc/Shelly.GetStatus")] = "<html>login</html>"
    asyncio.run(shelly.poll())
    assert value(states, f"switch.shelly_{G2}_1").value == "unavailable"


def test_offline_reads_unavailable_and_commands_say_so() -> None:
    shelly, states, fake = make(1)
    asyncio.run(shelly.poll())
    fake.offline = True
    asyncio.run(shelly.poll())
    for e in (f"switch.shelly_{G1}_0", f"sensor.shelly_{G1}_0_power", f"sensor.shelly_{G1}_0_energy"):
        assert value(states, e).value == "unavailable"
    with pytest.raises(ValueError, match=NOT_RESPONDING):
        asyncio.run(states.command(f"switch.shelly_{G1}_0", "turn_off", {}))


def test_detach_and_failing_device(caplog: pytest.LogCaptureFixture) -> None:
    shelly, states, fake = make(1)
    shelly.attach(Device("shelly", "665544332211", "192.168.1.61", "x", "Other", {}))

    async def flaky(method: str, host: str, path: str, **kw: Any) -> Any:
        if host == "192.168.1.61":
            raise RuntimeError("boom")
        return await fake(method, host, path, **kw)

    shelly.fetch = flaky
    asyncio.run(shelly.poll())  # one device's unexpected error must not stop the other
    assert value(states, f"switch.shelly_{G1}_0").value == "on"
    assert "boom" not in caplog.text
    shelly.detach(G1)
    shelly.detach("unknown")
    assert states.entity(f"switch.shelly_{G1}_0") is None
    asyncio.run(shelly._poll_one(G1))  # detached after poll() listed it: nothing to do


def test_restart_while_offline_then_recovery() -> None:
    _, _, fake = make(2)
    found, _ = asyncio.run(ShellyIntegration(StateMachine(EventBus()), None, fake).pair(HOST, None))  # type: ignore[arg-type]
    states = StateMachine(EventBus())
    shelly = ShellyIntegration(states, None, fake)  # type: ignore[arg-type]
    fake.offline = True  # CAVE restarts while the device is off
    shelly.attach(Device("shelly", found.device_id, HOST, found.model, found.name, found.settings))
    asyncio.run(shelly.poll())
    for n in (0, 1):
        assert value(states, f"switch.shelly_{G2}_{n}").value == "unavailable"
    assert not any(c[2] == "/shelly" for c in fake.calls[-2:])  # the saved generation is used
    fake.offline = False
    asyncio.run(shelly.poll())
    assert value(states, f"switch.shelly_{G2}_0").value == "on"
    assert value(states, f"sensor.shelly_{G2}_0_power").value == "40.2"
    fake.offline = True
    asyncio.run(shelly.poll())
    assert value(states, f"sensor.shelly_{G2}_0_power").value == "unavailable"
