"""config/mqtt.yaml: the broker, plus hand-written entities for devices that don't announce themselves."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from cave.integrations.mqtt.discovery import EntityConfig, Unsupported, build_config

# shortcut: errors name the key path but not the line number; Plan 4's YAML loader adds line numbers everywhere


@dataclass(frozen=True)
class Broker:
    host: str
    port: int = 1883
    username: str | None = None
    tls: bool = False


@dataclass(frozen=True)
class MqttConfig:
    broker: Broker
    discovery_prefix: str = "homeassistant"
    entities: tuple[EntityConfig, ...] = ()


class ConfigError(ValueError):
    pass


Scalar = str | bool | int | float


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Broker(_Strict):
    host: str = Field(min_length=1)
    port: int = Field(default=1883, ge=1, le=65535)
    username: str | None = None
    tls: bool = False


class _Entity(_Strict):
    component: Literal["light", "switch", "sensor", "binary_sensor", "cover", "lock", "button"]
    unique_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    state_topic: str | None = None
    command_topic: str | None = None
    value_template: str | None = None
    schema_: Literal["default", "json"] | None = Field(default=None, alias="schema")
    brightness: bool | None = None
    brightness_scale: int | None = Field(default=None, gt=0)
    brightness_state_topic: str | None = None
    brightness_command_topic: str | None = None
    unit_of_measurement: str | None = None
    device_class: str | None = None
    availability_topic: str | None = None
    payload_available: Scalar | None = None
    payload_not_available: Scalar | None = None
    payload_on: Scalar | None = None
    payload_off: Scalar | None = None
    state_on: Scalar | None = None
    state_off: Scalar | None = None
    payload_open: Scalar | None = None
    payload_close: Scalar | None = None
    payload_stop: Scalar | None = None
    state_open: Scalar | None = None
    state_closed: Scalar | None = None
    state_opening: Scalar | None = None
    state_closing: Scalar | None = None
    payload_lock: Scalar | None = None
    payload_unlock: Scalar | None = None
    state_locked: Scalar | None = None
    state_unlocked: Scalar | None = None
    payload_press: Scalar | None = None
    device: dict[str, str] | None = None

    @field_validator("command_topic", "brightness_command_topic")
    @classmethod
    def _no_wildcards(cls, v: str | None) -> str | None:
        if v is not None and ("+" in v or "#" in v or not v):
            raise ValueError("wildcards aren't allowed in a topic CAVE publishes to")
        return v


class _File(_Strict):
    broker: _Broker
    discovery_prefix: str = Field(default="homeassistant", min_length=1)
    entities: list[_Entity] = []


def _path(loc: tuple[int | str, ...]) -> str:
    out = ""
    for part in loc:
        out += f"[{part}]" if isinstance(part, int) else (f".{part}" if out else str(part))
    return out


def load(path: Path) -> MqttConfig | None:
    if not path.exists():
        return None
    name = path.name
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ConfigError(f"{name}: not valid YAML ({e})") from e
    if not isinstance(raw, dict):
        raise ConfigError(f"{name}: expected a mapping with a broker section")
    broker = raw.get("broker")
    if isinstance(broker, dict) and "password" in broker:
        raise ConfigError(
            f"{name}: broker.password: don't put the password in config files; set CAVE_MQTT_PASSWORD instead"
        )
    try:
        parsed = _File.model_validate(raw)
    except ValidationError as e:
        # a typo shows up as both "unknown key" and "missing key"; the unknown one is the useful message
        first = min(e.errors(), key=lambda err: err["type"] != "extra_forbidden")
        raise ConfigError(f"{name}: {_path(first['loc'])}: {first['msg']}") from e
    entities: list[EntityConfig] = []
    for i, ent in enumerate(parsed.entities):
        data = ent.model_dump(by_alias=True, exclude_none=True)
        component = data.pop("component")
        built = build_config(f"{name}:entities[{i}]", component, data, ent.unique_id, ent.unique_id)
        if isinstance(built, Unsupported):
            raise ConfigError(f"{name}: entities[{i}]: {built.reason}")
        entities.append(built)
    b = parsed.broker
    return MqttConfig(Broker(b.host, b.port, b.username, b.tls), parsed.discovery_prefix, tuple(entities))
