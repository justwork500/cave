"""Tests for the Plan 3 whole-branch review findings."""

import asyncio
import time

import aiomqtt
import pytest

from cave.integrations.mqtt import bridge as bridge_mod
from cave.integrations.mqtt import client as client_mod
from cave.integrations.mqtt.bridge import MqttBridge
from cave.integrations.mqtt.client import MqttService
from cave.integrations.mqtt.config import Broker, MqttConfig
from cave.integrations.mqtt.discovery import EntityConfig, Unsupported, build_config, parse_config
from cave.state import EventBus, StateMachine
from cave.templates import TemplateError, render_value
from tests.mqtt_fixtures import fixture, with_payload
from tests.test_mqtt_bridge import FakePublisher

P = "homeassistant"


def run(coro):
    return asyncio.run(coro)


def make(db):
    pub = FakePublisher()
    return MqttBridge(db, StateMachine(EventBus()), pub), pub


# ---- 1 (Critical): invalid subscribe topics ----

@pytest.mark.parametrize(
    "bad",
    ["a/#/b", "a/+", "#", "\ud800", "", "x" * 70000, "a\x00b"],
    ids=["hash", "plus", "all", "surrogate", "empty", "too-long", "nul"],
)
def test_bad_state_topic_dropped(bad):
    # through the shared builder: discovery payloads can't even carry a 70,000-char topic (64 KiB cap)
    c = build_config("t", "switch", {"name": "s", "unique_id": "s", "state_topic": bad, "availability_topic": bad,
                                     "command_topic": "ok/set"}, "s", "s")
    assert isinstance(c, EntityConfig) and c.state_topic is None and c.availability == ()
    if len(bad) < 1000:
        d = parse_config(*with_payload("tasmota_switch", stat_t=bad, avty_t=bad), P)
        assert isinstance(d, EntityConfig) and d.state_topic is None and d.availability == ()


# ---- 2 (Critical): component change for the same unique_id ----

def test_component_change_is_a_separate_entity(db):
    b, _ = make(db)
    run(b.handle(*fixture("z2m_lock")))
    topic, payload = fixture("z2m_lock")
    run(b.handle(topic.replace("/lock/", "/switch/", 1), payload))  # same unique_id, now a switch
    ids = {e.entity_id for e in b.states.entities()}
    assert "lock.front_door_lock" in ids and any(i.startswith("switch.") for i in ids)


# ---- 3 (Critical): template CPU and memory ----

@pytest.mark.parametrize("template", [
    "{% for a in range(100000) %}{% for b in range(100000) %}x{% endfor %}{% endfor %}",
    "{{ 'x' * 10000 * 1000 }}",
    "{{ ('x' * 10000) | replace('x', 'y' * 10000) }}",
    "{{ 'x' | center(10000000) }}",
    "{{ 'x' | indent(10000000, true) }}",
    "{{ '%010000000d' | format(1) }}",
    "{{ '%010000000d' % 1 }}",
    "{{ 'x'.ljust(10000000) }}",
    "{{ ((((9 ** 64) ** 64) ** 64) ** 64) ** 64 > 0 }}",
    "{{ range(100000) | join(',') }}",
])
def test_resource_bombs_refused(template):
    start = time.monotonic()
    with pytest.raises(TemplateError):
        render_value(template, '{"state": "ON"}')
    assert time.monotonic() - start < 1


@pytest.mark.parametrize(("template", "payload", "expected"), [
    ("{{ value_json.state }}", '{"state": "ON"}', "ON"),
    ("{{ value_json.t | float | round(1) }}", '{"t": "21.46"}', "21.5"),
    ("{{ 'ON' if value_json.power > 5 else 'OFF' }}", '{"power": 7}', "ON"),
    ("{{ value | int * 2 }}", "21", "42"),
    ("{{ (value_json.v | default(0)) / 10 }}", '{"v": 215}', "21.5"),
    ("{{ value_json.state | lower }}", '{"state": "ON"}', "on"),
    ("{{ '%.1f' % (value | float) }}", "21.46", "21.5"),
    ("{{ value_json['ENERGY']['Power'] }}", '{"ENERGY": {"Power": 12}}', "12"),
    ("{% if value_json.contact %}closed{% else %}open{% endif %}", '{"contact": true}', "closed"),
    ("{{ value_json.state is defined }}", "{}", "False"),
])
def test_ordinary_device_templates_still_work(template, payload, expected):
    assert render_value(template, payload) == expected


def test_discovery_refuses_disallowed_template():
    r = parse_config(*with_payload("z2m_contact", value_template="{{ 'x'.ljust(10) }}"), P)
    assert isinstance(r, Unsupported) and "template" in r.reason


# ---- 4 (Important): hijack through another discovery topic ----

def test_second_topic_cannot_take_over_entity(db):
    b, pub = make(db)
    run(b.handle(*fixture("z2m_lock")))
    _, payload = with_payload("z2m_lock", command_topic="evil/set")
    run(b.handle("homeassistant/lock/attacker/lock/config", payload))
    run(b.states.command("lock.front_door_lock", "unlock", {}))
    assert pub.calls == [("zigbee2mqtt/Front door lock/set", "UNLOCK", False)]
    assert any("another discovery topic" in u["reason"] for u in b.status()["unsupported"])


def test_binding_survives_restart(db):
    b, _ = make(db)
    run(b.handle(*fixture("z2m_lock")))
    b2, _ = make(db)
    _, payload = with_payload("z2m_lock", command_topic="evil/set")
    run(b2.handle("homeassistant/lock/attacker/lock/config", payload))
    assert b2.states.entity("lock.front_door_lock") is None  # the attacker's config was refused


def test_discovery_cannot_override_manual_entity(db):
    b, pub = make(db)
    manual = build_config("mqtt.yaml:entities[0]", "lock", {
        "unique_id": "0x000d6f000aabbccd_lock_zigbee2mqtt", "name": "Front door lock",
        "state_topic": "zigbee2mqtt/Front door lock", "command_topic": "zigbee2mqtt/Front door lock/set",
    }, "x", "x")
    assert isinstance(manual, EntityConfig)
    b.add_manual(manual)
    _, payload = with_payload("z2m_lock", command_topic="evil/set")
    run(b.handle(fixture("z2m_lock")[0], payload))
    run(b.states.command("lock.front_door_lock", "unlock", {}))
    assert pub.calls == [("zigbee2mqtt/Front door lock/set", "UNLOCK", False)]


# ---- 5 (Important): non-MqttError failures ----

def test_unexpected_error_in_loop_is_caught_and_reported(db, monkeypatch):
    class Boom:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            raise RuntimeError("something odd")

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(client_mod.aiomqtt, "Client", Boom)
    monkeypatch.setattr(client_mod, "backoff", lambda n: 30)
    service = MqttService(MqttConfig(Broker("x")), db, StateMachine(EventBus()), None)

    async def go():
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(service.run(), 0.3)

    run(go())
    assert service.status == "failed" and "something odd" in service.last_error


def test_bad_message_does_not_stop_the_loop(db, monkeypatch):
    class _Msg:
        def __init__(self, topic, payload):
            self.topic, self.payload = aiomqtt.Topic(topic), payload

    class Fake:
        def __init__(self, *a, **kw):
            self.subs = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def subscribe(self, topic, *a, **kw):
            self.subs.append(topic)

        @property
        def messages(self):
            async def gen():
                yield _Msg(*fixture("z2m_light_json"))
                yield _Msg(*fixture("tasmota_switch"))
                await asyncio.sleep(10)

            return gen()

    monkeypatch.setattr(client_mod.aiomqtt, "Client", Fake)
    states = StateMachine(EventBus())
    service = MqttService(MqttConfig(Broker("x")), db, states, None)
    real = service.bridge.handle

    async def flaky(topic, payload):
        if "light" in topic:
            raise RuntimeError("bridge bug")
        return await real(topic, payload)

    service.bridge.handle = flaky

    async def go():
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(service.run(), 0.3)

    run(go())
    assert states.entity("switch.garage_plug_garage_heater") is not None


# ---- 6 (Important): unbounded growth ----

def test_unsupported_list_is_capped(db, monkeypatch):
    monkeypatch.setattr(bridge_mod, "MAX_UNSUPPORTED", 3)
    b, _ = make(db)
    for i in range(10):
        run(b.handle(f"homeassistant/climate/n{i}/t/config", b'{"name": "t"}'))
    assert [u["topic"] for u in b.status()["unsupported"]] == [
        f"homeassistant/climate/n{i}/t/config" for i in (7, 8, 9)]


def test_cap_counts_removed_ids(db, monkeypatch):
    monkeypatch.setattr(bridge_mod, "MAX_ENTITIES", 2)
    b, _ = make(db)
    for i in range(3):
        topic, payload = with_payload("tasmota_switch", uniq_id=f"plug{i}")
        topic = topic.replace("8C4F00ABCDEF_RL_1", f"plug{i}")
        run(b.handle(topic, payload))
        run(b.handle(topic, b""))  # remove again
    assert db.execute("SELECT count(*) FROM mqtt_entities").fetchone()[0] == 2


def test_entity_id_length_capped(db):
    b, _ = make(db)
    run(b.handle(*with_payload("tasmota_switch", name="n" * 30000, dev={"name": "d"})))
    [e] = b.states.entities()
    assert len(e.entity_id.split(".", 1)[1]) <= 64


# ---- 7 (Important): batched subscriptions ----

def test_subscriptions_sent_in_one_call(db, monkeypatch):
    calls = []

    class Fake:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def subscribe(self, topic, *a, **kw):
            calls.append(topic)

        @property
        def messages(self):
            async def gen():
                await asyncio.sleep(10)
                yield None

            return gen()

    monkeypatch.setattr(client_mod.aiomqtt, "Client", Fake)
    cfg = MqttConfig(Broker("x"), entities=tuple(
        build_config(f"m{i}", "switch", {"unique_id": f"s{i}", "name": f"S{i}", "state_topic": f"s/{i}",
                                         "command_topic": f"s/{i}/set"}, "x", "x") for i in range(5)))
    service = MqttService(cfg, db, StateMachine(EventBus()), None)

    async def go():
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(service.run(), 0.3)

    run(go())
    assert len(calls) == 1 and isinstance(calls[0], list) and len(calls[0]) == 7  # 2 config wildcards + 5


def test_publish_failure_is_value_error(db):
    service = MqttService(MqttConfig(Broker("x")), db, StateMachine(EventBus()), None)

    class Broken:
        async def publish(self, *a, **kw):
            raise aiomqtt.MqttCodeError(4)

    service._client, service.status = Broken(), "connected"
    with pytest.raises(ValueError):
        run(service.bridge.publish("a/b", "x"))
