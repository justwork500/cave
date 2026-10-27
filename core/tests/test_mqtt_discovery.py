import json

from cave.integrations.mqtt.discovery import EntityConfig, Removal, Unsupported, parse_config, parse_topic
from tests.mqtt_fixtures import fixture, with_payload

P = "homeassistant"


def cfg(name: str) -> EntityConfig:
    result = parse_config(*fixture(name), P)
    assert isinstance(result, EntityConfig), result
    return result


def test_parse_topic_with_and_without_node():
    assert parse_topic("homeassistant/light/node1/lamp/config", P) == ("light", "node1", "lamp")
    assert parse_topic("homeassistant/switch/plug/config", P) == ("switch", None, "plug")
    assert parse_topic("homeassistant/light/node1/lamp/state", P) is None
    assert parse_topic("other/light/lamp/config", P) is None
    assert parse_config("zigbee2mqtt/Kitchen lamp", b"{}", P) is None


def test_z2m_light_json_schema():
    c = cfg("z2m_light_json")
    assert c.component == "light" and c.json_schema and c.brightness and c.brightness_scale == 254
    assert c.unique_id == "0x00158d0001a2b3c4_light_zigbee2mqtt"
    assert c.name == "Kitchen lamp"
    assert c.state_topic == "zigbee2mqtt/Kitchen lamp" and c.command_topic == "zigbee2mqtt/Kitchen lamp/set"
    assert ("zigbee2mqtt/Kitchen lamp/availability", "online", "offline", None) in c.availability
    assert ("zigbee2mqtt/bridge/state", "online", "offline", "{{ value_json.state }}") in c.availability
    assert c.device["manufacturer"] == "IKEA" and c.device["model"] == "LED1836G9"
    assert not c.read_only


def test_z2m_contact_name_and_template():
    c = cfg("z2m_contact")
    assert c.component == "binary_sensor" and c.name == "Back door Door"
    assert c.value_template == "{{ value_json.contact }}"
    assert (c.payload_on, c.payload_off) == ("False", "True")  # JSON booleans normalised to rendered form
    assert c.device_class == "door"


def test_tasmota_abbreviations_and_tilde():
    c = cfg("tasmota_switch")
    assert c.state_topic == "tasmota_ABCDEF/stat/RESULT"
    assert c.command_topic == "tasmota_ABCDEF/cmnd/POWER"
    assert c.availability == (("tasmota_ABCDEF/tele/LWT", "Online", "Offline", None),)
    assert c.value_template == "{{value_json.POWER}}"
    assert c.unique_id == "8C4F00ABCDEF_RL_1" and c.name == "Garage plug Garage heater"
    assert c.device == {"name": "Garage plug", "manufacturer": "Tasmota", "model": "Sonoff S31"}


def test_shelly_cover_payloads():
    c = cfg("shelly_cover")
    assert (c.payload_open, c.payload_close, c.payload_stop) == ("open", "close", "stop")
    assert (c.state_open, c.state_closed, c.state_opening, c.state_closing) == ("open", "closed", "opening", "closing")


def test_esphome_sensor():
    c = cfg("esphome_sensor")
    assert c.component == "sensor" and c.unit == "°C" and c.device_class == "temperature"
    assert c.availability == (("garage-node/status", "online", "offline", None),)
    assert c.read_only  # sensors take no commands


def test_unique_id_falls_back_to_topic():
    topic, payload = fixture("button")
    data = json.loads(payload)
    del data["unique_id"]
    c = parse_config(topic, json.dumps(data).encode(), P)
    assert isinstance(c, EntityConfig) and c.unique_id == "doorbell-node_chime_test"


def test_empty_payload_is_removal():
    topic, _ = fixture("z2m_light_json")
    assert parse_config(topic, b"", P) == Removal(topic)


def test_unsupported_component():
    r = parse_config("homeassistant/climate/node/thermostat/config", b'{"name": "t"}', P)
    assert isinstance(r, Unsupported) and "not supported" in r.reason


def test_unsupported_light_schema():
    r = parse_config(*with_payload("z2m_light_json", schema="template"), P)
    assert isinstance(r, Unsupported)


def test_wildcard_command_topic_makes_read_only():  # Review Focus 2
    c = parse_config(*with_payload("tasmota_switch", cmd_t="a/+/set"), P)
    assert isinstance(c, EntityConfig) and c.read_only and c.command_topic is None
    b = parse_config(*with_payload("button", command_topic="doorbell/#"), P)
    assert isinstance(b, Unsupported)


def test_missing_command_topic_makes_read_only():  # Review Focus 2
    c = parse_config(*with_payload("z2m_lock", command_topic=""), P)
    assert isinstance(c, EntityConfig) and c.read_only and c.command_topic is None
    b = parse_config(*with_payload("button", command_topic=None), P)
    assert isinstance(b, Unsupported)


def test_oversize_and_non_json_unsupported():
    topic, _ = fixture("button")
    assert isinstance(parse_config(topic, b"x" * (64 * 1024 + 1), P), Unsupported)
    assert isinstance(parse_config(topic, b"\xff\xfe not utf8", P), Unsupported)
    assert isinstance(parse_config(topic, b"not json", P), Unsupported)
    assert isinstance(parse_config(topic, b"[1, 2]", P), Unsupported)


def test_long_template_unsupported():
    r = parse_config(*with_payload("z2m_contact", value_template="{{ value }}" + " " * 2001), P)
    assert isinstance(r, Unsupported)
