"""The shared control vocabulary: validates commands for media_player, number and select.

Integrations call `check_command` first in their command handler. A `ValueError`
carries a sentence a person can read; the API turns it into a 409.
"""

import math
from collections.abc import Callable, Mapping
from typing import Any

_MEDIA_PLAIN = {"turn_on", "turn_off", "toggle", "play", "pause", "play_pause"}


def _num(raw: Any) -> float | None:
    if isinstance(raw, bool):
        return None
    try:
        result = float(raw)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _volume_set(args: Mapping[str, Any], _attrs: Mapping[str, Any]) -> dict[str, Any]:
    level = _num(args.get("level"))
    if level is None or level != int(level) or not 0 <= level <= 100:
        raise ValueError("The volume level must be a whole number from 0 to 100.")
    return {"level": int(level)}


def _volume_mute(args: Mapping[str, Any], _attrs: Mapping[str, Any]) -> dict[str, Any]:
    muted = str(args.get("muted")).lower()
    if muted not in ("true", "false"):
        raise ValueError("Muted must be true or false.")
    return {"muted": muted == "true"}


def _pick(key: str, listing: str, noun: str) -> Callable[[Mapping[str, Any], Mapping[str, Any]], dict[str, Any]]:
    def check(args: Mapping[str, Any], attrs: Mapping[str, Any]) -> dict[str, Any]:
        choice = args.get(key)
        if choice not in (attrs.get(listing) or []):
            raise ValueError(f"This device has no {noun} called {choice}.")
        return {key: choice}

    return check


def _set_value(args: Mapping[str, Any], attrs: Mapping[str, Any]) -> dict[str, Any]:
    low = _num(attrs.get("min"))
    high = _num(attrs.get("max"))
    step = _num(attrs.get("step"))
    low = 0.0 if low is None else low
    high = 100.0 if high is None else high
    step = 1.0 if step is None or step <= 0 else step
    value = _num(args.get("value"))
    if value is None:
        raise ValueError("The value must be a number.")
    if not low <= value <= high:
        raise ValueError(f"The value must be from {low:g} to {high:g}.")
    snapped = low + round((value - low) / step) * step
    snapped = min(snapped, high)
    return {"value": int(snapped) if snapped == int(snapped) else round(snapped, 10)}


_Check = Callable[[Mapping[str, Any], Mapping[str, Any]], dict[str, Any]]

_COMMANDS: dict[str, dict[str, _Check]] = {
    "media_player": {
        **{c: (lambda _a, _t: {}) for c in _MEDIA_PLAIN},
        "volume_set": _volume_set,
        "volume_mute": _volume_mute,
        "select_source": _pick("source", "sources", "source"),
    },
    "number": {"set_value": _set_value},
    "select": {"select_option": _pick("option", "options", "option")},
}


def check_command(
    capability: str, command: str, args: Mapping[str, Any], attributes: Mapping[str, Any]
) -> dict[str, Any]:
    """Return the cleaned args for a command, or raise ValueError saying why not."""
    table = _COMMANDS.get(capability)
    if table is None:
        return dict(args)
    check = table.get(command)
    if check is None:
        raise ValueError(f"This device can't {command.replace('_', ' ')}.")
    return check(args, attributes)
