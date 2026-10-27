"""MQTT messages <-> CAVE states and commands, for one EntityConfig. Pure: no network, no registry."""

import json
import logging
from typing import Any

from cave.integrations.mqtt.discovery import EntityConfig
from cave.templates import TemplateError, render_value

log = logging.getLogger(__name__)
MAX_STATE_BYTES = 256 * 1024
StateValue = tuple[str, dict[str, Any]]


class CommandError(ValueError):
    pass


def topics_for(cfg: EntityConfig) -> set[str]:
    topics = {t for t in (cfg.state_topic, cfg.brightness_state_topic) if t}
    return topics | {a[0] for a in cfg.availability}


def _base_attrs(cfg: EntityConfig) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    if cfg.unit:
        attrs["unit_of_measurement"] = cfg.unit
    if cfg.device_class:
        attrs["device_class"] = cfg.device_class
    return attrs


def _render(cfg: EntityConfig, template: str | None, text: str) -> str | None:
    if template is None:
        return text
    try:
        return render_value(template, text)
    except TemplateError as e:
        log.warning("template for %s failed: %s", cfg.unique_id, e)
        return None


def _on_off(cfg: EntityConfig, value: str) -> str | None:
    on, off = cfg.state_on or cfg.payload_on, cfg.state_off or cfg.payload_off

    def same(a: str, b: str) -> bool:
        # templates render JSON booleans as True/False; devices may configure true/false
        return a == b or (a.lower() in ("true", "false") and a.lower() == b.lower())

    if same(value, on):
        return "on"
    if same(value, off):
        return "off"
    return None


def _scale_in(cfg: EntityConfig, raw: Any) -> int | None:
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        return None
    return max(0, min(255, round(raw * 255 / cfg.brightness_scale)))


def _availability(cfg: EntityConfig, topic: str, text: str, current: StateValue | None) -> StateValue | None:
    for t, available, not_available, template in cfg.availability:
        if t != topic:
            continue
        value = _render(cfg, template, text)
        attrs = dict(current[1]) if current else {}
        if value == not_available:
            return "unavailable", attrs
        if value == available:
            if current is None or current[0] == "unavailable":
                return "unknown", attrs
            return current
    return None


def state_from_message(cfg: EntityConfig, topic: str, payload: bytes, current: StateValue | None) -> StateValue | None:
    """The new (value, attributes) for this message, or None to leave the state as it is."""
    if cfg.component == "button" or len(payload) > MAX_STATE_BYTES:
        return None
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return None
    available = _availability(cfg, topic, text, current)
    if available is not None:
        return available
    attrs = {**(current[1] if current else {}), **_base_attrs(cfg)}

    if cfg.component == "light" and topic == cfg.brightness_state_topic:
        try:
            level = _scale_in(cfg, float(text))
        except ValueError:
            return None
        if level is None:
            return None
        return (current[0] if current else "unknown"), {**attrs, "brightness": level}

    if topic != cfg.state_topic:
        return None

    if cfg.component == "light" and cfg.json_schema:
        try:
            data = json.loads(text)
        except ValueError:
            return None
        if not isinstance(data, dict) or not isinstance(data.get("state"), str):
            return None
        state = _on_off(cfg, data["state"])
        if state is None:
            return None
        level = _scale_in(cfg, data.get("brightness"))
        return state, ({**attrs, "brightness": level} if level is not None else attrs)

    value = _render(cfg, cfg.value_template, text)
    if value is None:
        return None
    if cfg.component in ("switch", "light", "binary_sensor"):
        state = _on_off(cfg, value)
        return (state, attrs) if state else None
    if cfg.component == "cover":
        states = {cfg.state_open: "open", cfg.state_closed: "closed",
                  cfg.state_opening: "opening", cfg.state_closing: "closing"}
        return (states[value], attrs) if value in states else None
    if cfg.component == "lock":
        states = {cfg.state_locked: "locked", cfg.state_unlocked: "unlocked"}
        return (states[value], attrs) if value in states else None
    return value, attrs  # sensor


def _brightness_arg(cfg: EntityConfig, args: dict[str, Any]) -> int | None:
    if "brightness" not in args:
        return None
    b = args["brightness"]
    if isinstance(b, bool) or not isinstance(b, int) or not 0 <= b <= 255:
        raise CommandError("Brightness must be a whole number from 0 to 255.")
    return round(b * cfg.brightness_scale / 255)


def command_to_publish(cfg: EntityConfig, command: str, args: dict[str, Any]) -> list[tuple[str, str]]:
    """(topic, payload) pairs that carry out a CAVE command on this device."""
    if cfg.read_only or cfg.command_topic is None:
        raise CommandError("This device only reports; it can't be controlled.")
    t = cfg.command_topic
    simple = {
        "switch": {"turn_on": cfg.payload_on, "turn_off": cfg.payload_off},
        "cover": {"open": cfg.payload_open, "close": cfg.payload_close, "stop": cfg.payload_stop},
        "lock": {"lock": cfg.payload_lock, "unlock": cfg.payload_unlock},
        "button": {"press": cfg.payload_press},
    }.get(cfg.component)
    if simple is not None:
        if command not in simple:
            raise CommandError(f"This device doesn't support {command!r}.")
        return [(t, simple[command])]
    if command not in ("turn_on", "turn_off"):  # light
        raise CommandError(f"This device doesn't support {command!r}.")
    level = _brightness_arg(cfg, args) if command == "turn_on" else None
    if cfg.json_schema:
        body: dict[str, Any] = {"state": "ON" if command == "turn_on" else "OFF"}
        if level is not None:
            body["brightness"] = level
        return [(t, json.dumps(body))]
    out = [(t, cfg.payload_on if command == "turn_on" else cfg.payload_off)]
    if level is not None and cfg.brightness_command_topic:
        out.append((cfg.brightness_command_topic, str(level)))
    return out
