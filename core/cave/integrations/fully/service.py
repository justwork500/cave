"""Fully Kiosk Browser tablets (Remote Administration REST API): screen, brightness and battery, polled.

The Remote Administration password is part of every request's query, so it is never logged, put in an error
or returned.
"""

import asyncio
import logging
import re
from typing import Any
from urllib.parse import quote

from cave.credentials import Credentials
from cave.integrations.base import Device, Found, Pairing, PairingError
from cave.integrations.http import NOT_RESPONDING, DeviceError, Fetch, request
from cave.state import Entity, StateMachine

log = logging.getLogger(__name__)
POLL_SECONDS = 15.0
PORT = 2323
BAD_REPLY = (KeyError, TypeError, ValueError, AttributeError, IndexError)  # an HTML page, odd types
INFO = "cmd=deviceInfo&type=json"


def _clean(device_id: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(device_id).lower())


def _entities(tablet: str) -> dict[str, tuple[str, dict[str, Any]]]:
    return {
        f"switch.fully_{tablet}_screen": ("Screen", {}),
        f"number.fully_{tablet}_brightness": ("Brightness", {"min": 0, "max": 255, "step": 1}),
        f"sensor.fully_{tablet}_battery": ("Battery", {"unit": "%"}),
    }


class FullyKioskIntegration:
    domain = "fully"
    title = "Fully Kiosk Browser"
    pairing: Pairing = "password"
    pairing_hint = "The Remote Administration password set in Fully Kiosk's settings."

    def __init__(self, states: StateMachine, credentials: Credentials, fetch: Fetch = request) -> None:
        self.states, self.credentials, self.fetch = states, credentials, fetch
        self._hosts: dict[str, str] = {}  # tablet id -> address
        self._entities: dict[str, set[str]] = {}  # tablet id -> its registered entities

    async def _get(self, host: str, query: str, password: str | None) -> Any:
        extra = "" if password is None else f"&password={quote(password, safe='')}"
        return await self.fetch("GET", host, f"/?{query}{extra}", port=PORT)

    async def probe(self, host: str) -> Found | None:
        info = await self._get(host, INFO, None)
        if not isinstance(info, dict):
            return None
        if "deviceID" in info:
            return Found(_clean(info["deviceID"]), host, str(info.get("deviceModel", "")),
                         str(info.get("deviceName") or "Fully Kiosk Browser"))
        if info.get("status") == "Error" and "login" in str(info.get("statustext", "")).lower():
            return Found("", host, "Fully Kiosk Browser", "Fully Kiosk Browser")  # the id is known after pairing
        return None

    async def pair(self, host: str, secret: str | None) -> tuple[Found, dict[str, str]]:
        password = secret or ""
        try:
            info = await self._get(host, INFO, password)
            if not isinstance(info, dict):
                raise PairingError("This doesn't look like a Fully Kiosk Browser tablet.")
            if "deviceID" not in info:
                raise PairingError("That password didn't work. Check Remote Administration in Fully Kiosk's settings.")
            tablet = _clean(info["deviceID"])
            found = Found(tablet, host, str(info.get("deviceModel", "")), str(info.get("deviceName") or "Fully Kiosk Browser"))
        except (DeviceError, *BAD_REPLY):
            raise PairingError("This doesn't look like a Fully Kiosk Browser tablet.") from None
        if not tablet:
            raise PairingError("This tablet didn't report an id CAVE can use.")
        return found, {"password": password}

    def attach(self, device: Device) -> None:
        t = device.device_id
        self._hosts[t] = device.host
        self._entities[t] = set()
        for entity, (name, attributes) in _entities(t).items():  # so an offline tablet shows as unavailable
            self.states.register(Entity(entity, f"{device.name} {name}", None, entity.split(".", 1)[0]))
            self._entities[t].add(entity)
            if not entity.startswith("sensor."):
                self.states.set_entity_handler(entity, self._handler)
            self.states.set(entity, "unavailable", attributes)

    def detach(self, device_id: str) -> None:
        self._hosts.pop(device_id, None)
        for entity in self._entities.pop(device_id, set()):
            self.states.remove(entity)

    def _set(self, entity: str, value: str) -> None:
        current = self.states.get(entity)
        if current is None:  # it may have been detached meanwhile
            return
        self.states.set(entity, value, dict(current.attributes))  # keep the attributes so tiles still draw

    async def _poll_one(self, tablet: str) -> None:
        host = self._hosts.get(tablet)
        if host is None:  # detached since poll() listed it
            return
        known = self._entities.get(tablet, set())
        password = self.credentials.get("fully", f"{tablet}:password")
        if password is None:
            log.warning("Fully Kiosk tablet %s: its saved password can't be read. Remove the tablet and add it again.", tablet)
            for entity in known:
                self._set(entity, "unavailable")
            return
        try:
            info = await self._get(host, INFO, password)
            values = {
                f"switch.fully_{tablet}_screen": "on" if info["screenOn"] else "off",
                f"number.fully_{tablet}_brightness": str(int(info["screenBrightness"])),
                f"sensor.fully_{tablet}_battery": str(int(info["batteryLevel"])),
            }
        except (DeviceError, *BAD_REPLY) as e:
            log.warning("Fully Kiosk tablet %s: %s", tablet, e if isinstance(e, DeviceError) else "unexpected reply")
            for entity in known:
                self._set(entity, "unavailable")
            return
        if tablet not in self._hosts:  # detached while we waited
            return
        for entity, value in values.items():
            self._set(entity, value)

    async def poll(self) -> None:
        tablets = list(self._hosts)
        # One tablet's unexpected error is logged and must not stop the others, or run().
        results = await asyncio.gather(*(self._poll_one(t) for t in tablets), return_exceptions=True)
        for tablet, result in zip(tablets, results, strict=True):
            if isinstance(result, Exception):
                log.error("Fully Kiosk tablet %s: polling failed (%s).", tablet, type(result).__name__)

    async def run(self) -> None:
        while True:
            await self.poll()
            await asyncio.sleep(POLL_SECONDS)

    async def _handler(self, entity: str, command: str, args: dict[str, Any]) -> None:
        tablet = entity.split(".", 1)[1].removeprefix("fully_").rpartition("_")[0]
        password = self.credentials.get("fully", f"{tablet}:password")
        if tablet not in self._hosts or password is None:
            raise ValueError(NOT_RESPONDING)
        current = self.states.get(entity)
        if entity.startswith("number."):
            level = int(args["value"])
            query, new = f"cmd=setStringSetting&key=screenBrightness&value={level}", str(level)
        else:
            on = command == "turn_on" or (command == "toggle" and (current is None or current.value != "on"))
            query, new = f"cmd={'screenOn' if on else 'screenOff'}", "on" if on else "off"
        try:
            reply = await self._get(self._hosts[tablet], query, password)
        except DeviceError as e:
            raise ValueError(NOT_RESPONDING) from e
        if isinstance(reply, dict) and reply.get("status") == "Error":
            raise ValueError("The tablet refused the command.")
        self._set(entity, new)
