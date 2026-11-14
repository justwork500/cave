"""Philips Hue bridges (v1 local API over HTTP): lights, motion and temperature sensors, polled.

The bridge key is part of every request path, so it is never logged, put in an error or returned.
"""

import asyncio
import logging
from dataclasses import replace
from typing import Any

from cave.credentials import Credentials
from cave.integrations.base import Device, Found, Pairing, PairingError
from cave.integrations.http import NOT_RESPONDING, DeviceError, Fetch, request
from cave.state import Entity, StateMachine

log = logging.getLogger(__name__)
POLL_SECONDS = 15.0
BAD_REPLY = (KeyError, TypeError, ValueError, AttributeError, IndexError)  # an HTML page, a list error reply, odd types
Reading = tuple[str, str, dict[str, Any]]  # name, value, attributes


def _ids(bridge: str, settings: dict[str, Any], default: str) -> dict[str, str]:
    """Entity id -> name, from the numbers (and names) saved at pairing; an older save is a list without names."""
    def name(saved: Any, n: str, kind: str) -> str:
        return str(saved[n]) if isinstance(saved, dict) else f"{default} {kind} {n}"

    out: dict[str, str] = {}
    for kind, pattern in (("light", "light.hue_{b}_{n}"), ("motion", "binary_sensor.hue_{b}_{n}_motion"),
                          ("temperature", "sensor.hue_{b}_{n}_temperature")):
        saved = settings.get("lights" if kind == "light" else kind, [])
        for n in saved:
            out[pattern.format(b=bridge, n=n)] = name(saved, n, kind)
    return out


def _readings(bridge: str, lights: dict[str, Any], sensors: dict[str, Any]) -> dict[str, Reading]:
    out: dict[str, Reading] = {}
    for n, light in lights.items():
        st = light["state"]
        bri = {"brightness": round(int(st["bri"]) * 255 / 254)} if "bri" in st else {}
        value = ("on" if st["on"] else "off") if st["reachable"] else "unavailable"
        out[f"light.hue_{bridge}_{n}"] = (str(light["name"]), value, bri)
    for n, sensor in sensors.items():
        if sensor["type"] == "ZLLPresence":
            out[f"binary_sensor.hue_{bridge}_{n}_motion"] = (
                str(sensor["name"]), "on" if sensor["state"]["presence"] else "off", {})
        elif sensor["type"] == "ZLLTemperature":
            temp = f"{int(sensor['state']['temperature']) / 100:.1f}"
            out[f"sensor.hue_{bridge}_{n}_temperature"] = (str(sensor["name"]), temp, {"unit": "°C"})
    return out


def _numbers(lights: dict[str, Any], sensors: dict[str, Any]) -> dict[str, dict[str, str]]:
    kinds = {"ZLLPresence": "motion", "ZLLTemperature": "temperature"}
    out: dict[str, dict[str, str]] = {"lights": {n: str(v["name"]) for n, v in lights.items()}, "motion": {},
                                      "temperature": {}}
    for n, sensor in sensors.items():
        if sensor["type"] in kinds:
            out[kinds[sensor["type"]]][n] = str(sensor["name"])
    return out


class HueIntegration:
    domain = "hue"
    title = "Philips Hue"
    pairing: Pairing = "button"
    pairing_hint = "Press the round button on top of the Hue bridge, then choose Add within 30 seconds."

    def __init__(self, states: StateMachine, credentials: Credentials, fetch: Fetch = request) -> None:
        self.states, self.credentials, self.fetch = states, credentials, fetch
        self._hosts: dict[str, str] = {}  # bridge id -> address
        self._entities: dict[str, set[str]] = {}  # bridge id -> its registered entities, so they can read unavailable

    async def probe(self, host: str) -> Found | None:
        info = await self.fetch("GET", host, "/api/config")
        if not isinstance(info, dict) or "bridgeid" not in info:
            return None
        return Found(str(info["bridgeid"]).lower(), host, str(info.get("modelid", "")), str(info.get("name") or "Hue Bridge"))

    async def pair(self, host: str, secret: str | None) -> tuple[Found, dict[str, str]]:
        try:
            found = await self.probe(host)
            if found is None:
                raise PairingError("This doesn't look like a Hue bridge.")
            reply = await self.fetch("POST", host, "/api", body={"devicetype": "cave#hub"})
            if "error" in reply[0]:
                if reply[0]["error"]["type"] == 101:
                    raise PairingError("Press the button on the Hue bridge first, then choose Add again.")
                raise PairingError("The Hue bridge refused to pair.")
            key = str(reply[0]["success"]["username"])
            lights = await self.fetch("GET", host, f"/api/{key}/lights")
            sensors = await self.fetch("GET", host, f"/api/{key}/sensors")
            settings = _numbers(lights, sensors)
        except (DeviceError, *BAD_REPLY):
            raise PairingError("This doesn't look like a Hue bridge.") from None
        return replace(found, settings=settings), {"key": key}

    def attach(self, device: Device) -> None:
        b = device.device_id
        self._hosts[b] = device.host
        self._entities[b] = set()
        for entity, name in _ids(b, device.settings, device.name).items():  # so an offline bridge shows as unavailable
            self._put(b, entity, name, "unavailable", {})

    def detach(self, device_id: str) -> None:
        self._hosts.pop(device_id, None)
        for entity in self._entities.pop(device_id, set()):
            self.states.remove(entity)

    def _set(self, entity: str, value: str, attributes: dict[str, Any] | None = None) -> None:
        if self.states.entity(entity) is None:  # it may have been detached meanwhile
            return
        if attributes is None:  # keep the last attributes so tiles still draw
            current = self.states.get(entity)
            attributes = dict(current.attributes) if current else {}
        self.states.set(entity, value, attributes)

    def _put(self, bridge: str, entity: str, name: str, value: str, attributes: dict[str, Any] | None) -> None:
        if self.states.entity(entity) is None:
            domain = entity.split(".", 1)[0]
            self.states.register(Entity(entity, name, None, domain))
            self._entities[bridge].add(entity)
            if domain == "light":
                self.states.set_entity_handler(entity, self._handler)
        self._set(entity, value, attributes)

    async def _poll_one(self, bridge: str) -> None:
        host = self._hosts.get(bridge)
        if host is None:  # detached since poll() listed it
            return
        known = self._entities.get(bridge, set())
        key = self.credentials.get("hue", f"{bridge}:key")
        if key is None:
            log.warning("Hue bridge %s: its saved key can't be read. Remove the bridge and add it again.", bridge)
            for entity in known:
                self._set(entity, "unavailable")
            return
        try:
            lights = await self.fetch("GET", host, f"/api/{key}/lights")
            sensors = await self.fetch("GET", host, f"/api/{key}/sensors")
            readings = _readings(bridge, lights, sensors)
        except (DeviceError, *BAD_REPLY) as e:
            log.warning("Hue bridge %s: %s", bridge, e if isinstance(e, DeviceError) else "unexpected reply")
            for entity in known:
                self._set(entity, "unavailable")
            return
        if bridge not in self._hosts:  # detached while we waited
            return
        for entity in known - readings.keys():  # a light or sensor the bridge no longer lists
            self._set(entity, "unavailable")
        for entity, (name, value, attributes) in readings.items():
            self._put(bridge, entity, name, value, attributes or None)

    async def poll(self) -> None:
        bridges = list(self._hosts)
        # One bridge's unexpected error is logged and must not stop the others, or run().
        results = await asyncio.gather(*(self._poll_one(b) for b in bridges), return_exceptions=True)
        for bridge, result in zip(bridges, results, strict=True):
            if isinstance(result, Exception):
                log.error("Hue bridge %s: polling failed (%s).", bridge, type(result).__name__)

    async def run(self) -> None:
        while True:
            await self.poll()
            await asyncio.sleep(POLL_SECONDS)

    async def _handler(self, entity: str, command: str, args: dict[str, Any]) -> None:
        bridge, _, n = entity.split(".", 1)[1].removeprefix("hue_").rpartition("_")
        key = self.credentials.get("hue", f"{bridge}:key")
        if bridge not in self._hosts or key is None:
            raise ValueError(NOT_RESPONDING)
        current = self.states.get(entity)
        on = command == "turn_on" or (command == "toggle" and (current is None or current.value != "on"))
        body: dict[str, Any] = {"on": on}
        attrs = dict(current.attributes) if current else {}
        if "brightness" in args:
            body["bri"] = max(1, round(int(args["brightness"]) * 254 / 255))
            attrs["brightness"] = args["brightness"]
        try:
            reply = await self.fetch("PUT", self._hosts[bridge], f"/api/{key}/lights/{n}/state", body=body)
        except DeviceError as e:
            raise ValueError(NOT_RESPONDING) from e
        if any("error" in item for item in reply):
            raise ValueError("The Hue bridge refused the command.")
        self._set(entity, "on" if on else "off", attrs)
