import asyncio
import json

import pytest

from cave.access.evaluate import can_control
from cave.api.deps import principal_for_user
from cave.integrations.mqtt import bridge as bridge_mod
from cave.integrations.mqtt.bridge import MqttBridge
from cave.state import EventBus, StateMachine
from tests.access_fixtures import LAN, LOCAL
from tests.conftest import T0, sign_in
from tests.mqtt_fixtures import fixture, with_payload


class FakePublisher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, bool]] = []

    async def __call__(self, topic: str, payload: str, retain: bool) -> None:
        self.calls.append((topic, payload, retain))


def run(coro):
    return asyncio.run(coro)


def make(db, states=None):
    pub = FakePublisher()
    return MqttBridge(db, states or StateMachine(EventBus()), pub), pub


LAMP = "light.kitchen_lamp"


def test_subscriptions_include_config_wildcards(db):
    b, _ = make(db)
    assert {"homeassistant/+/+/config", "homeassistant/+/+/+/config"} <= b.subscriptions()


def test_discovered_light_registers_and_takes_state(db):
    b, _ = make(db)
    new = run(b.handle(*fixture("z2m_light_json")))
    assert "zigbee2mqtt/Kitchen lamp" in new and "zigbee2mqtt/Kitchen lamp" in b.subscriptions()
    e = b.states.entity(LAMP)
    assert e is not None and e.name == "Kitchen lamp" and e.capability == "light"
    run(b.handle("zigbee2mqtt/Kitchen lamp", json.dumps({"state": "ON", "brightness": 254}).encode()))
    s = b.states.get(LAMP)
    assert s.value == "on" and s.attributes["brightness"] == 255 and s.attributes["device"]["manufacturer"] == "IKEA"


def test_replayed_config_keeps_entity_id(db):  # Review Focus 1
    b, _ = make(db)
    run(b.handle(*fixture("z2m_light_json")))
    run(b.handle(*fixture("z2m_light_json")))
    assert [e.entity_id for e in b.states.entities()] == [LAMP]
    b2, _ = make(db)  # restart: new bridge, same database
    run(b2.handle(*fixture("z2m_light_json")))
    assert [e.entity_id for e in b2.states.entities()] == [LAMP]


def test_renamed_device_keeps_entity_id(db):
    b, _ = make(db)
    run(b.handle(*fixture("z2m_light_json")))
    topic, payload = with_payload("z2m_light_json", device={"name": "Pantry lamp"})
    run(b.handle(topic, payload))
    assert b.states.entity(LAMP).name == "Pantry lamp"


def test_name_collision_gets_suffix(db):
    b, _ = make(db)
    run(b.handle(*fixture("z2m_light_json")))
    topic, payload = with_payload("z2m_light_json", unique_id="another_lamp")
    run(b.handle(topic.replace("0x00158d0001a2b3c4", "0xother"), payload))
    assert {e.entity_id for e in b.states.entities()} == {LAMP, "light.kitchen_lamp_2"}


def test_removal_removes_entity_and_ignores_later_state(db):  # Review Focus 4
    b, _ = make(db)
    topic, _ = fixture("z2m_light_json")
    run(b.handle(*fixture("z2m_light_json")))
    run(b.handle(topic, b""))
    assert b.states.entity(LAMP) is None
    run(b.handle("zigbee2mqtt/Kitchen lamp", json.dumps({"state": "ON"}).encode()))
    assert b.states.entities() == []
    run(b.handle(*fixture("z2m_light_json")))  # the device comes back with the same id
    assert b.states.entity(LAMP) is not None


def test_state_before_config_ignored(db):  # Review Focus 4
    b, _ = make(db)
    run(b.handle("zigbee2mqtt/Kitchen lamp", json.dumps({"state": "ON"}).encode()))
    assert b.states.entities() == []


def test_command_publishes_via_handler(db):
    b, pub = make(db)
    run(b.handle(*with_payload("z2m_light_json", brightness_scale=255)))
    run(b.states.command(LAMP, "turn_on", {"brightness": 128}))
    assert pub.calls == [("zigbee2mqtt/Kitchen lamp/set", json.dumps({"state": "ON", "brightness": 128}), False)]


def test_toggle_uses_current_state(db):
    b, pub = make(db)
    run(b.handle(*fixture("tasmota_switch")))
    sid = "switch.garage_plug_garage_heater"
    run(b.states.command(sid, "toggle", {}))
    run(b.handle("tasmota_ABCDEF/stat/RESULT", b'{"POWER": "ON"}'))
    run(b.states.command(sid, "toggle", {}))
    assert [c[1] for c in pub.calls] == ["ON", "OFF"]


def test_read_only_command_rejected(db):
    b, pub = make(db)
    run(b.handle(*fixture("esphome_sensor")))
    with pytest.raises(ValueError):
        run(b.states.command("sensor.garage_node_garage_temperature", "turn_on", {}))
    assert pub.calls == []


def test_publish_rejects_wildcards(db):
    b, pub = make(db)
    for bad in ("a/#", "a/+/b", ""):
        with pytest.raises(ValueError):
            run(b.publish(bad, "x"))
    run(b.publish("garage/heater/set", "ON", retain=True))
    assert pub.calls == [("garage/heater/set", "ON", True)]


def test_entity_cap(db, monkeypatch):
    monkeypatch.setattr(bridge_mod, "MAX_ENTITIES", 2)
    b, _ = make(db)
    for name in ("z2m_light_json", "tasmota_switch", "z2m_lock"):
        run(b.handle(*fixture(name)))
    assert len(b.states.entities()) == 2
    assert any(u["reason"] == "too many MQTT entities" for u in b.status()["unsupported"])


def test_unsupported_recorded_once(db):
    b, _ = make(db)
    for _ in range(3):
        run(b.handle("homeassistant/climate/node/t/config", b'{"name": "t"}'))
    assert b.status() == {"entities": 0, "unsupported": [
        {"topic": "homeassistant/climate/node/t/config", "reason": "component not supported in this version"}]}


def test_hostile_template_does_not_crash_bridge(db):  # Review Focus 3
    b, _ = make(db)
    run(b.handle(*with_payload("z2m_contact", value_template="{{ ''.__class__.__mro__ }}")))
    run(b.handle("zigbee2mqtt/Back door", b'{"contact": true}'))
    assert b.states.get("binary_sensor.back_door_door") is None


def test_discovered_entity_is_admin_only_until_on_an_item(app, users):
    b = MqttBridge(app.state.db, app.state.states, FakePublisher())
    run(b.handle(*fixture("z2m_light_json")))
    sam = principal_for_user(app.state.db, users.sam, T0)
    admin = principal_for_user(app.state.db, users.admin, T0)
    assert not can_control(app.state.db, sam, LAMP, LAN, LOCAL)
    assert can_control(app.state.db, admin, LAMP, LAN, LOCAL)


def test_rest_command_on_read_only_is_409(app, client, users):
    b = MqttBridge(app.state.db, app.state.states, FakePublisher())
    run(b.handle(*fixture("esphome_sensor")))
    sign_in(client, "admin", "pw-admin-1234", users.admin_totp)
    r = client.post("/api/v1/entities/sensor.garage_node_garage_temperature/commands/turn_on", json={})
    assert r.status_code == 409 and r.json() == {"detail": "This device only reports; it can't be controlled."}
