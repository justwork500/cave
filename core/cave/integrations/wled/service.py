"""WLED lights: on/off, brightness and the preset list, polled over WLED's JSON API. Nothing secret to store."""

import asyncio
import logging
from typing import Any

from cave.credentials import Credentials
from cave.integrations.base import Device, Found, Pairing, PairingError
from cave.integrations.http import NOT_RESPONDING, DeviceError, Fetch, request
from cave.state import Entity, StateMachine

log = logging.getLogger(__name__)
POLL_SECONDS = 15.0
BAD_REPLY = (KeyError, TypeError, ValueError, AttributeError)  # an HTML page, a missing key, odd types


class WledIntegration:
    domain = "wled"
    title = "WLED"
    pairing: Pairing = "none"
    pairing_hint = ""

    def __init__(self, states: StateMachine, credentials: Credentials, fetch: Fetch = request) -> None:
        self.states, self.fetch = states, fetch
        self._hosts: dict[str, str] = {}  # MAC -> address
        self._presets: dict[str, dict[str, int]] = {}  # MAC -> preset name -> id, from the last poll

    async def probe(self, host: str) -> Found | None:
        info = await self.fetch("GET", host, "/json/info")
        if not isinstance(info, dict) or info.get("brand") != "WLED":
            return None
        return Found(str(info["mac"]).lower(), host, str(info["arch"]), str(info["name"]))

    async def pair(self, host: str, secret: str | None) -> tuple[Found, dict[str, str]]:
        try:
            found = await self.probe(host)
        except (DeviceError, *BAD_REPLY):
            found = None
        if found is None:
            raise PairingError("This doesn't look like a WLED device.")
        return found, {}

    def attach(self, device: Device) -> None:
        mac = device.device_id
        self._hosts[mac] = device.host
        self.states.register(Entity(self._light(mac), device.name, None, "light"))
        self.states.register(Entity(self._select(mac), f"{device.name} preset", None, "select"))
        self.states.set_entity_handler(self._light(mac), self._handler)
        self.states.set_entity_handler(self._select(mac), self._handler)

    def detach(self, device_id: str) -> None:
        self._hosts.pop(device_id, None)
        self._presets.pop(device_id, None)
        self.states.remove(self._light(device_id))
        self.states.remove(self._select(device_id))

    @staticmethod
    def _light(mac: str) -> str:
        return f"light.wled_{mac}"

    @staticmethod
    def _select(mac: str) -> str:
        return f"select.wled_{mac}_preset"

    def _attrs(self, entity: str) -> dict[str, Any]:
        current = self.states.get(entity)
        return dict(current.attributes) if current else {}

    def _set(self, entity: str, value: str, attributes: dict[str, Any]) -> None:
        if self.states.entity(entity) is not None:  # it may have been detached meanwhile
            self.states.set(entity, value, attributes)

    async def _poll_one(self, mac: str) -> None:
        host = self._hosts.get(mac)
        if host is None:  # detached since poll() listed it
            return
        try:
            state = await self.fetch("GET", host, "/json/state")
            raw = await self.fetch("GET", host, "/presets.json")
            presets = {str(p["n"]): int(i) for i, p in sorted(raw.items(), key=lambda kv: int(kv[0]))
                       if i != "0" and "n" in p}
            on, bri, ps = bool(state["on"]), int(state["bri"]), str(state.get("ps", -1))
            active = str(raw[ps]["n"]) if ps in raw and "n" in raw[ps] else ""
        except (DeviceError, *BAD_REPLY) as e:
            log.warning("WLED device %s: %s", mac, e if isinstance(e, DeviceError) else "unexpected reply")
            for entity in (self._light(mac), self._select(mac)):  # keep the last attributes so tiles still draw
                self._set(entity, "unavailable", self._attrs(entity))
            return
        self._presets[mac] = presets
        self._set(self._light(mac), "on" if on else "off", {"brightness": bri})
        self._set(self._select(mac), active, {"options": list(presets)})

    async def poll(self) -> None:
        macs = list(self._hosts)
        # One device's unexpected error is logged and must not stop the others, or run().
        results = await asyncio.gather(*(self._poll_one(m) for m in macs), return_exceptions=True)
        for mac, result in zip(macs, results, strict=True):
            if isinstance(result, Exception):
                log.error("WLED device %s: polling failed (%s).", mac, type(result).__name__)

    async def run(self) -> None:
        while True:
            await self.poll()
            await asyncio.sleep(POLL_SECONDS)

    async def _handler(self, entity: str, command: str, args: dict[str, Any]) -> None:
        mac = entity.split(".", 1)[1].removeprefix("wled_").removesuffix("_preset")
        if mac not in self._hosts:
            raise KeyError(entity)
        attrs = self._attrs(entity)
        if command == "select_option":
            body: dict[str, Any] = {"ps": self._presets[mac][args["option"]]}
        else:
            current = self.states.get(entity)
            on = command == "turn_on" or (command == "toggle" and (current is None or current.value != "on"))
            body = {"on": on}
            if "brightness" in args:
                body["bri"] = attrs["brightness"] = args["brightness"]
        try:
            await self.fetch("POST", self._hosts[mac], "/json/state", body=body)
        except DeviceError as e:
            raise ValueError(NOT_RESPONDING) from e
        self._set(entity, args["option"] if command == "select_option" else "on" if body["on"] else "off", attrs)
