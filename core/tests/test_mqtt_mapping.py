import json

import pytest

from cave.integrations.mqtt.discovery import EntityConfig, parse_config
from cave.integrations.mqtt.mapping import CommandError, command_to_publish, state_from_message, topics_for
from tests.mqtt_fixtures import fixture, with_payload


def cfg(name: str, **changes: object) -> EntityConfig:
    c = parse_config(*(with_payload(name, **changes) if changes else fixture(name)), "homeassistant")
    assert isinstance(c, EntityConfig), c
    return c


def j(obj: object) -> bytes:
    return json.dumps(obj).encode()


def test_topics_for_light():
    c = cfg("z2m_light_json")
    assert topics_for(c) == {"zigbee2mqtt/Kitchen lamp", "zigbee2mqtt/Kitchen lamp/availability",
                             "zigbee2mqtt/bridge/state"}


def test_z2m_light_state_and_brightness():
    c = cfg("z2m_light_json")
    assert state_from_message(c, c.state_topic, j({"state": "ON", "brightness": 254}), None) == (
        "on", {"brightness": 255})
    assert state_from_message(c, c.state_topic, j({"state": "OFF", "brightness": 127}), None) == (
        "off", {"brightness": 128})


def test_z2m_contact_boolean_payloads():
    c = cfg("z2m_contact")
    assert state_from_message(c, c.state_topic, j({"contact": False}), None) == ("on", {"device_class": "door"})
    assert state_from_message(c, c.state_topic, j({"contact": True}), None)[0] == "off"


def test_tasmota_switch_on_off():
    c = cfg("tasmota_switch")
    assert state_from_message(c, c.state_topic, j({"POWER": "ON"}), None)[0] == "on"
    assert state_from_message(c, c.state_topic, j({"POWER": "OFF"}), None)[0] == "off"
    assert state_from_message(c, c.state_topic, j({"POWER": "WEIRD"}), None) is None
    assert state_from_message(c, c.state_topic, j({"Dimmer": 50}), None) is None  # other RESULT messages


def test_cover_states():
    c = cfg("shelly_cover")
    for s in ("open", "closed", "opening", "closing"):
        assert state_from_message(c, c.state_topic, j({"state": s}), None)[0] == s
    assert state_from_message(c, c.state_topic, j({"state": "stopped"}), None) is None


def test_lock_states():
    c = cfg("z2m_lock")
    assert state_from_message(c, c.state_topic, j({"state": "LOCK"}), None)[0] == "locked"
    assert state_from_message(c, c.state_topic, j({"state": "UNLOCK"}), None)[0] == "unlocked"


def test_sensor_value_and_unit():
    c = cfg("esphome_sensor")
    assert state_from_message(c, c.state_topic, b"21.5", None) == (
        "21.5", {"unit_of_measurement": "°C", "device_class": "temperature"})


def test_availability_offline_then_online_keeps_value():
    c = cfg("esphome_sensor")
    attrs = {"unit_of_measurement": "°C", "device_class": "temperature"}
    assert state_from_message(c, "garage-node/status", b"offline", ("21.5", attrs)) == ("unavailable", attrs)
    assert state_from_message(c, "garage-node/status", b"online", ("21.5", attrs)) == ("21.5", attrs)
    assert state_from_message(c, "garage-node/status", b"online", None) == ("unknown", {})


def test_availability_with_template():
    c = cfg("z2m_light_json")
    assert state_from_message(c, "zigbee2mqtt/bridge/state", j({"state": "offline"}), ("on", {}))[0] == "unavailable"


def test_bad_payloads_keep_state():  # Review Focus 5
    light = cfg("z2m_light_json")
    for bad in (b"\xff\xfe", b"not json", b"[1]", b"x" * (256 * 1024 + 1)):
        assert state_from_message(light, light.state_topic, bad, ("on", {})) is None
    contact = cfg("z2m_contact")
    assert state_from_message(contact, contact.state_topic, b"not json", ("on", {})) is None


def test_hostile_template_keeps_state():  # Review Focus 3
    c = cfg("z2m_contact", value_template="{{ ''.__class__.__mro__ }}")
    assert state_from_message(c, c.state_topic, j({"contact": True}), ("on", {})) is None


def test_button_never_has_state():
    c = cfg("button")
    assert state_from_message(c, "anything", b"x", None) is None


def test_commands_per_component():
    assert command_to_publish(cfg("tasmota_switch"), "turn_on", {}) == [("tasmota_ABCDEF/cmnd/POWER", "ON")]
    assert command_to_publish(cfg("tasmota_switch"), "turn_off", {}) == [("tasmota_ABCDEF/cmnd/POWER", "OFF")]
    light = cfg("z2m_light_json", brightness_scale=255)
    assert command_to_publish(light, "turn_on", {"brightness": 128}) == [
        ("zigbee2mqtt/Kitchen lamp/set", json.dumps({"state": "ON", "brightness": 128}))]
    assert command_to_publish(light, "turn_off", {}) == [("zigbee2mqtt/Kitchen lamp/set", json.dumps({"state": "OFF"}))]
    scaled = cfg("z2m_light_json")  # scale 254
    assert command_to_publish(scaled, "turn_on", {"brightness": 255}) == [
        ("zigbee2mqtt/Kitchen lamp/set", json.dumps({"state": "ON", "brightness": 254}))]
    plain = cfg("tasmota_switch")
    plain_light = EntityConfig(**{**plain.__dict__, "component": "light", "brightness": True,
                                  "brightness_command_topic": "lamp/bri/set"})
    assert command_to_publish(plain_light, "turn_on", {"brightness": 255}) == [
        ("tasmota_ABCDEF/cmnd/POWER", "ON"), ("lamp/bri/set", "255")]
    assert command_to_publish(cfg("shelly_cover"), "stop", {}) == [
        ("shellyplus2pm-a8032ab1c2d3/command/cover:0", "stop")]
    assert command_to_publish(cfg("z2m_lock"), "unlock", {}) == [("zigbee2mqtt/Front door lock/set", "UNLOCK")]
    assert command_to_publish(cfg("button"), "press", {}) == [("doorbell-node/button/chime_test/command", "PRESS")]


def test_read_only_and_bad_args_raise():
    with pytest.raises(CommandError):
        command_to_publish(cfg("esphome_sensor"), "turn_on", {})
    with pytest.raises(CommandError):
        command_to_publish(cfg("tasmota_switch", cmd_t="a/#"), "turn_on", {})
    with pytest.raises(CommandError):
        command_to_publish(cfg("tasmota_switch"), "explode", {})
    light = cfg("z2m_light_json")
    for bad in (-1, 256, "bright", True, 1.5):
        with pytest.raises(CommandError):
            command_to_publish(light, "turn_on", {"brightness": bad})
