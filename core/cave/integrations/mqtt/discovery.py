"""MQTT discovery: turn `<prefix>/<component>/[<node_id>/]<object_id>/config` messages into EntityConfig.

The topic and payload format is an open protocol published by Zigbee2MQTT, Tasmota, Shelly and ESPHome.
Everything here is pure: no network, no state.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, cast, get_args

Component = Literal["light", "switch", "sensor", "binary_sensor", "cover", "lock", "button"]
COMPONENTS: frozenset[str] = frozenset(get_args(Component))
CONTROLLABLE = frozenset({"light", "switch", "cover", "lock", "button"})

MAX_CONFIG_BYTES = 64 * 1024
MAX_TEMPLATE_CHARS = 2000

ABBREVIATIONS: Mapping[str, str] = {
    "avty": "availability",
    "avty_t": "availability_topic",
    "avty_tpl": "availability_template",
    "bri_cmd_t": "brightness_command_topic",
    "bri_scl": "brightness_scale",
    "bri_stat_t": "brightness_state_topic",
    "cmd_t": "command_topic",
    "dev": "device",
    "dev_cla": "device_class",
    "name": "name",
    "pl_avail": "payload_available",
    "pl_cls": "payload_close",
    "pl_lock": "payload_lock",
    "pl_not_avail": "payload_not_available",
    "pl_off": "payload_off",
    "pl_on": "payload_on",
    "pl_open": "payload_open",
    "pl_prs": "payload_press",
    "pl_stop": "payload_stop",
    "pl_unlk": "payload_unlock",
    "stat_closing": "state_closing",
    "stat_clsd": "state_closed",
    "stat_locked": "state_locked",
    "stat_off": "state_off",
    "stat_on": "state_on",
    "stat_open": "state_open",
    "stat_opening": "state_opening",
    "stat_t": "state_topic",
    "stat_unlocked": "state_unlocked",
    "t": "topic",
    "uniq_id": "unique_id",
    "unit_of_meas": "unit_of_measurement",
    "val_tpl": "value_template",
}
DEVICE_ABBREVIATIONS: Mapping[str, str] = {"mf": "manufacturer", "mdl": "model", "sw": "sw_version", "ids": "identifiers"}
TOPIC_KEYS = frozenset({
    "state_topic", "command_topic", "availability_topic", "brightness_state_topic", "brightness_command_topic", "topic",
})


@dataclass(frozen=True)
class EntityConfig:
    component: Component
    unique_id: str
    name: str
    state_topic: str | None = None
    command_topic: str | None = None
    value_template: str | None = None
    json_schema: bool = False
    payload_on: str = "ON"
    payload_off: str = "OFF"
    state_on: str | None = None
    state_off: str | None = None
    payload_open: str = "OPEN"
    payload_close: str = "CLOSE"
    payload_stop: str = "STOP"
    state_open: str = "open"
    state_closed: str = "closed"
    state_opening: str = "opening"
    state_closing: str = "closing"
    payload_lock: str = "LOCK"
    payload_unlock: str = "UNLOCK"
    state_locked: str = "LOCKED"
    state_unlocked: str = "UNLOCKED"
    payload_press: str = "PRESS"
    brightness: bool = False
    brightness_scale: int = 255
    brightness_state_topic: str | None = None
    brightness_command_topic: str | None = None
    unit: str | None = None
    device_class: str | None = None
    # (topic, available payload, not-available payload, value template or None)
    availability: tuple[tuple[str, str, str, str | None], ...] = ()
    device: Mapping[str, str] = field(default_factory=dict)
    read_only: bool = False


@dataclass(frozen=True)
class Removal:
    topic: str


@dataclass(frozen=True)
class Unsupported:
    topic: str
    reason: str


def parse_topic(topic: str, prefix: str) -> tuple[str, str | None, str] | None:
    parts = topic.split("/")
    if parts[0] != prefix or parts[-1] != "config":
        return None
    if len(parts) == 4:
        return parts[1], None, parts[2]
    if len(parts) == 5:
        return parts[1], parts[2], parts[3]
    return None


def _as_payload(value: Any) -> str:
    """Payloads may be JSON booleans or numbers; compare them as a template would render them."""
    if isinstance(value, bool):
        return "True" if value else "False"
    return str(value)


def _expand(data: Mapping[str, Any]) -> dict[str, Any]:
    out = {ABBREVIATIONS.get(k, k): v for k, v in data.items()}
    base = out.get("~")
    if isinstance(base, str):
        for key in TOPIC_KEYS & out.keys():
            v = out[key]
            if isinstance(v, str):
                if v.startswith("~"):
                    v = base + v[1:]
                elif v.endswith("~"):
                    v = v[:-1] + base
                out[key] = v
    return out


def _topic(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _safe_command_topic(value: Any) -> str | None:
    t = _topic(value)
    return None if t is None or "+" in t or "#" in t else t


def _availability(d: Mapping[str, Any]) -> tuple[tuple[str, str, str, str | None], ...]:
    entries: list[tuple[str, str, str, str | None]] = []
    raw = d.get("availability")
    items = raw if isinstance(raw, list) else []
    if _topic(d.get("availability_topic")):
        items = [*items, {"topic": d["availability_topic"], "payload_available": d.get("payload_available"),
                          "payload_not_available": d.get("payload_not_available"),
                          "value_template": d.get("availability_template")}]
    for item in items:
        if not isinstance(item, Mapping):
            continue
        item = {ABBREVIATIONS.get(k, k): v for k, v in item.items()}
        t = _topic(item.get("topic"))
        if t is None:
            continue
        tpl = item.get("value_template")
        entries.append((
            t,
            _as_payload(item.get("payload_available") or "online"),
            _as_payload(item.get("payload_not_available") or "offline"),
            tpl if isinstance(tpl, str) else None,
        ))
    return tuple(entries)


def _device(raw: Any) -> dict[str, str]:
    if not isinstance(raw, Mapping):
        return {}
    d = {DEVICE_ABBREVIATIONS.get(k, k): v for k, v in raw.items()}
    return {k: str(d[k]) for k in ("name", "manufacturer", "model", "sw_version") if isinstance(d.get(k), str | int)}


def _name(d: Mapping[str, Any], device: Mapping[str, str], object_id: str) -> str:
    own = d.get("name") if isinstance(d.get("name"), str) else None
    dev = device.get("name")
    if own and dev and not own.lower().startswith(dev.lower()):
        return f"{dev} {own}"
    return own or dev or object_id


def build_config(
    topic: str, component: str, raw: Mapping[str, Any], fallback_unique_id: str, object_id: str
) -> EntityConfig | Unsupported:
    """Shared by discovery and config/mqtt.yaml, so both behave the same."""
    if component not in COMPONENTS:
        return Unsupported(topic, "component not supported in this version")
    d = _expand(raw)
    if component == "light" and d.get("schema", "default") not in ("default", "json"):
        return Unsupported(topic, "light schema not supported in this version")
    templates = [d.get("value_template")] + [a[3] for a in _availability(d)]
    if any(isinstance(t, str) and len(t) > MAX_TEMPLATE_CHARS for t in templates):
        return Unsupported(topic, "template too long")
    command_topic = _safe_command_topic(d.get("command_topic"))
    if component == "button" and command_topic is None:
        return Unsupported(topic, "button without a usable command topic")
    device = _device(d.get("device"))
    kwargs: dict[str, Any] = {
        "component": cast(Component, component),
        "unique_id": str(d.get("unique_id") or fallback_unique_id),
        "name": _name(d, device, object_id),
        "state_topic": _topic(d.get("state_topic")),
        "command_topic": command_topic,
        "value_template": d["value_template"] if isinstance(d.get("value_template"), str) else None,
        "json_schema": d.get("schema") == "json",
        "brightness": bool(d.get("brightness")) or _topic(d.get("brightness_command_topic")) is not None,
        "brightness_state_topic": _topic(d.get("brightness_state_topic")),
        "brightness_command_topic": _safe_command_topic(d.get("brightness_command_topic")),
        "unit": d["unit_of_measurement"] if isinstance(d.get("unit_of_measurement"), str) else None,
        "device_class": d["device_class"] if isinstance(d.get("device_class"), str) else None,
        "availability": _availability(d),
        "device": device,
        "read_only": component not in CONTROLLABLE or command_topic is None,
    }
    if isinstance(d.get("brightness_scale"), int) and d["brightness_scale"] > 0:
        kwargs["brightness_scale"] = d["brightness_scale"]
    for key in (
        "payload_on", "payload_off", "state_on", "state_off", "payload_open", "payload_close", "payload_stop",
        "state_open", "state_closed", "state_opening", "state_closing", "payload_lock", "payload_unlock",
        "state_locked", "state_unlocked", "payload_press",
    ):
        if d.get(key) is not None and not isinstance(d[key], Mapping | list):
            kwargs[key] = _as_payload(d[key])
    return EntityConfig(**kwargs)


def parse_config(topic: str, payload: bytes, prefix: str) -> EntityConfig | Removal | Unsupported | None:
    parsed = parse_topic(topic, prefix)
    if parsed is None:
        return None
    component, node_id, object_id = parsed
    if len(payload) > MAX_CONFIG_BYTES:
        return Unsupported(topic, "config too large")
    if not payload:
        return Removal(topic)
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return Unsupported(topic, "config is not valid JSON")
    if not isinstance(data, dict):
        return Unsupported(topic, "config is not a JSON object")
    fallback = f"{node_id}_{object_id}" if node_id else object_id
    return build_config(topic, component, data, fallback, object_id)
