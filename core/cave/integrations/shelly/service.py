"""Shelly relays (gen 1 and gen 2+): switches with power and energy sensors, polled over HTTP. No password support."""

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
BAD_REPLY = (KeyError, TypeError, ValueError, AttributeError)  # an HTML page, a missing key, odd types


def _generation(info: Any) -> int:
    """1 or 2+ from a /shelly reply; 0 if it isn't a Shelly."""
    if not isinstance(info, dict) or "mac" not in info:
        return 0
    if int(info.get("gen", 0)) >= 2:
        return int(info["gen"])
    return 1 if "type" in info else 0


def _status_path(gen: int) -> str:
    return "/rpc/Shelly.GetStatus" if gen >= 2 else "/status"


def _channels(gen: int, status: Any) -> dict[int, dict[str, Any]]:
    """Channel -> {on, power?, energy?} (energy in kWh) from a status reply."""
    out: dict[int, dict[str, Any]] = {}
    if gen < 2:
        meters = status.get("meters") or []
        for n, relay in enumerate(status.get("relays") or []):
            ch: dict[str, Any] = {"on": bool(relay["ison"])}
            if n < len(meters) and "power" in meters[n]:
                ch["power"] = float(meters[n]["power"])
            if n < len(meters) and "total" in meters[n]:
                ch["energy"] = round(float(meters[n]["total"]) / 60000, 3)  # watt-minutes
            out[n] = ch
    else:
        for key, sw in status.items():
            if key.startswith("switch:"):
                ch = {"on": bool(sw["output"])}
                if "apower" in sw:
                    ch["power"] = float(sw["apower"])
                if "total" in sw.get("aenergy", {}):
                    ch["energy"] = round(float(sw["aenergy"]["total"]) / 1000, 3)  # Wh
                out[int(key[7:])] = ch
    return out


class ShellyIntegration:
    domain = "shelly"
    title = "Shelly"
    pairing: Pairing = "none"
    pairing_hint = ""

    def __init__(self, states: StateMachine, credentials: Credentials, fetch: Fetch = request) -> None:
        self.states, self.fetch = states, fetch
        self._hosts: dict[str, str] = {}  # MAC -> address
        self._names: dict[str, str] = {}  # MAC -> device name
        self._gen: dict[str, int] = {}  # MAC -> generation, saved at pairing, or read on the first poll
        self._seen: dict[str, set[int]] = {}  # MAC -> channels reported so far, so they can read unavailable

    async def probe(self, host: str) -> Found | None:
        info = await self.fetch("GET", host, "/shelly")
        gen = _generation(info)
        if gen == 0:
            return None
        model = str(info["model"] if gen >= 2 else info["type"])
        return Found(str(info["mac"]).lower(), host, model, str(info.get("name") or model) if gen >= 2 else model)

    async def pair(self, host: str, secret: str | None) -> tuple[Found, dict[str, str]]:
        try:
            info = await self.fetch("GET", host, "/shelly")
            found = await self.probe(host)
            if found is None:
                raise PairingError("This doesn't look like a Shelly device.")
            gen = _generation(info)
            if info.get("auth_en" if gen >= 2 else "auth"):
                raise PairingError("This Shelly has a password set. CAVE can't use password-protected Shelly devices yet.")
            channels = _channels(gen, await self.fetch("GET", host, _status_path(gen)))
            if not channels:
                raise PairingError("CAVE supports Shelly relays for now, not dimmers or colour lights.")
        except (DeviceError, *BAD_REPLY):
            raise PairingError("This doesn't look like a Shelly device.") from None
        return replace(found, settings={"gen": 1 if gen < 2 else 2, "channels": len(channels)}), {}

    def attach(self, device: Device) -> None:
        mac = device.device_id
        self._hosts[mac] = device.host
        self._names[mac] = device.name
        channels = int(device.settings.get("channels", 0))  # an older save has none: found on the first poll
        if "gen" in device.settings:
            self._gen[mac] = int(device.settings["gen"])
        self._seen[mac] = set(range(channels))
        for n in range(channels):  # so an offline device shows as unavailable; sensors appear once reported
            self._put(mac, self._entities(mac, n)[0], self._label(mac, n), "unavailable", {})

    def detach(self, device_id: str) -> None:
        self._hosts.pop(device_id, None)
        self._names.pop(device_id, None)
        self._gen.pop(device_id, None)
        for n in self._seen.pop(device_id, set()):
            for entity in self._entities(device_id, n):
                self.states.remove(entity)

    @staticmethod
    def _entities(mac: str, n: int) -> list[str]:
        return [f"switch.shelly_{mac}_{n}", f"sensor.shelly_{mac}_{n}_power", f"sensor.shelly_{mac}_{n}_energy"]

    def _set(self, entity: str, value: str, attributes: dict[str, Any] | None = None) -> None:
        if self.states.entity(entity) is None:  # it may have been detached meanwhile
            return
        if attributes is None:  # keep the last attributes so tiles still draw
            current = self.states.get(entity)
            attributes = dict(current.attributes) if current else {}
        self.states.set(entity, value, attributes)

    def _put(self, mac: str, entity: str, label: str, value: str, attributes: dict[str, Any]) -> None:
        if self.states.entity(entity) is None:
            self.states.register(Entity(entity, f"{self._names[mac]}{label}", None, entity.split(".", 1)[0]))
            if entity.startswith("switch."):
                self.states.set_entity_handler(entity, self._handler)
        self._set(entity, value, attributes)

    def _label(self, mac: str, n: int) -> str:
        return f" {n + 1}" if len(self._seen[mac]) > 1 else ""

    def _unavailable(self, mac: str, channels: set[int]) -> None:
        for n in channels:
            for entity in self._entities(mac, n):
                self._set(entity, "unavailable")

    async def _poll_one(self, mac: str) -> None:
        host = self._hosts.get(mac)
        if host is None:  # detached since poll() listed it
            return
        seen = self._seen.get(mac, set())
        try:
            gen = self._gen.get(mac) or _generation(await self.fetch("GET", host, "/shelly"))
            if gen == 0:
                raise ValueError("not a Shelly reply")
            channels = _channels(gen, await self.fetch("GET", host, _status_path(gen)))
        except (DeviceError, *BAD_REPLY) as e:
            log.warning("Shelly device %s: %s", mac, e if isinstance(e, DeviceError) else "unexpected reply")
            self._unavailable(mac, seen)
            return
        if mac not in self._hosts:  # detached while we waited
            return
        self._gen[mac] = gen
        seen = self._seen.setdefault(mac, set())
        seen.update(channels)
        self._unavailable(mac, seen - channels.keys())  # a channel the device stopped reporting
        for n, ch in channels.items():
            switch, power, energy = self._entities(mac, n)
            label = self._label(mac, n)
            self._put(mac, switch, label, "on" if ch["on"] else "off", {})
            if "power" in ch:
                self._put(mac, power, f"{label} power", str(ch["power"]), {"unit": "W"})
            if "energy" in ch:
                self._put(mac, energy, f"{label} energy", str(ch["energy"]), {"unit": "kWh"})

    async def poll(self) -> None:
        macs = list(self._hosts)
        # One device's unexpected error is logged and must not stop the others, or run().
        results = await asyncio.gather(*(self._poll_one(m) for m in macs), return_exceptions=True)
        for mac, result in zip(macs, results, strict=True):
            if isinstance(result, Exception):
                log.error("Shelly device %s: polling failed (%s).", mac, type(result).__name__)

    async def run(self) -> None:
        while True:
            await self.poll()
            await asyncio.sleep(POLL_SECONDS)

    async def _handler(self, entity: str, command: str, args: dict[str, Any]) -> None:
        mac, _, n = entity.split(".", 1)[1].removeprefix("shelly_").rpartition("_")
        if mac not in self._hosts or mac not in self._gen:
            raise KeyError(entity)
        if self._gen[mac] < 2:
            turn = "toggle" if command == "toggle" else "on" if command == "turn_on" else "off"
            path = f"/relay/{n}?turn={turn}"
        elif command == "toggle":
            path = f"/rpc/Switch.Toggle?id={n}"
        else:
            path = f"/rpc/Switch.Set?id={n}&on={'true' if command == 'turn_on' else 'false'}"
        try:
            await self.fetch("GET", self._hosts[mac], path)
        except DeviceError as e:
            raise ValueError(NOT_RESPONDING) from e
        current = self.states.get(entity)
        on = command == "turn_on" or (command == "toggle" and (current is None or current.value != "on"))
        self._set(entity, "on" if on else "off")
