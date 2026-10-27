import pytest

from cave.integrations.mqtt.config import Broker, ConfigError, load
from cave.integrations.mqtt.discovery import parse_config


def write(tmp_path, text: str):
    p = tmp_path / "mqtt.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_missing_file_is_none(tmp_path):
    assert load(tmp_path / "mqtt.yaml") is None


def test_minimal_broker(tmp_path):
    cfg = load(write(tmp_path, "broker:\n  host: mosquitto\n"))
    assert cfg.broker == Broker(host="mosquitto") and cfg.discovery_prefix == "homeassistant" and cfg.entities == ()


MANUAL = """\
broker:
  host: 192.168.1.2
  port: 1884
  username: cave
discovery_prefix: discovery
entities:
  - component: switch
    unique_id: garage_heater
    name: Garage heater
    state_topic: garage/heater/state
    command_topic: garage/heater/set
"""


def test_manual_entity_equals_discovery_equivalent(tmp_path):
    cfg = load(write(tmp_path, MANUAL))
    assert cfg.broker == Broker(host="192.168.1.2", port=1884, username="cave")
    assert cfg.discovery_prefix == "discovery"
    discovered = parse_config(
        "homeassistant/switch/garage_heater/config",
        b'{"unique_id": "garage_heater", "name": "Garage heater", "state_topic": "garage/heater/state",'
        b' "command_topic": "garage/heater/set"}',
        "homeassistant",
    )
    assert cfg.entities == (discovered,)


def test_unknown_key_rejected_with_path(tmp_path):
    with pytest.raises(ConfigError, match=r"mqtt\.yaml: entities\[0\]\.colour"):
        load(write(tmp_path, MANUAL + "    colour: red\n"))
    with pytest.raises(ConfigError, match=r"mqtt\.yaml: brokr"):
        load(write(tmp_path, "brokr:\n  host: x\n"))


def test_password_key_rejected(tmp_path):
    with pytest.raises(ConfigError, match="CAVE_MQTT_PASSWORD"):
        load(write(tmp_path, "broker:\n  host: x\n  password: hunter2\n"))


def test_wildcard_command_topic_rejected(tmp_path):
    with pytest.raises(ConfigError, match=r"entities\[0\]\.command_topic"):
        load(write(tmp_path, MANUAL.replace("garage/heater/set", "garage/+/set")))


def test_unsupported_component_rejected(tmp_path):
    with pytest.raises(ConfigError, match=r"entities\[0\]\.component"):
        load(write(tmp_path, MANUAL.replace("component: switch", "component: climate")))


def test_bad_yaml_is_config_error(tmp_path):
    with pytest.raises(ConfigError, match="mqtt.yaml"):
        load(write(tmp_path, "broker: [unclosed\n"))
    with pytest.raises(ConfigError, match="broker"):
        load(write(tmp_path, "discovery_prefix: x\n"))
