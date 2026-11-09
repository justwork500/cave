"""The registry every Phase 2 integration plugs into: probe, pair, attach, detach, run."""

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from cave.credentials import Credentials
from cave.db import Database

log = logging.getLogger(__name__)
Pairing = Literal["none", "password", "key", "pin", "button"]
PROBE_SECONDS = 5.0


@dataclass(frozen=True)
class Found:
    device_id: str  # MAC (lowercase hex, no separators) or serial
    host: str
    model: str
    name: str


@dataclass(frozen=True)
class Device:
    integration: str
    device_id: str
    host: str
    model: str
    name: str
    settings: dict[str, Any]


class PairingError(Exception):
    """Its message is shown to the Admin as is."""


class Integration(Protocol):
    domain: str
    title: str
    pairing: Pairing
    pairing_hint: str

    async def probe(self, host: str) -> Found | None: ...
    async def pair(self, host: str, secret: str | None) -> tuple[Found, dict[str, str]]: ...
    def attach(self, device: Device) -> None: ...
    def detach(self, device_id: str) -> None: ...
    async def run(self) -> None: ...


class Integrations:
    def __init__(self, db: Database, credentials: Credentials) -> None:
        self._db = db
        self._credentials = credentials
        self._by_domain: dict[str, Integration] = {}

    def register(self, integration: Integration) -> None:
        self._by_domain[integration.domain] = integration

    def get(self, domain: str) -> Integration | None:
        return self._by_domain.get(domain)

    def all(self) -> list[Integration]:
        return list(self._by_domain.values())

    def devices(self, domain: str) -> list[Device]:
        rows = self._db.execute("SELECT * FROM integration_devices WHERE integration = ? ORDER BY device_id",
                                (domain,)).fetchall()
        return [Device(r["integration"], r["device_id"], r["host"], r["model"], r["name"],
                       json.loads(r["settings"])) for r in rows]

    def load(self) -> None:
        for integration in self.all():
            for device in self.devices(integration.domain):
                try:
                    integration.attach(device)
                except Exception:
                    log.exception("Could not attach %s device %s; skipping it.", integration.domain,
                                  device.device_id)

    async def run(self) -> None:
        await asyncio.gather(*(i.run() for i in self.all()))

    async def probe(self, domain: str, host: str) -> Found | None:
        try:
            return await asyncio.wait_for(self._by_domain[domain].probe(host), PROBE_SECONDS)
        except TimeoutError:
            return None

    async def add(self, domain: str, host: str, secret: str | None, actor: str) -> tuple[Device, bool]:
        integration = self._by_domain[domain]
        found, creds = await integration.pair(host, secret)
        for key, value in creds.items():
            self._credentials.set(domain, f"{found.device_id}:{key}", value, actor)
        existing = next((d for d in self.devices(domain) if d.device_id == found.device_id), None)
        device = Device(domain, found.device_id, host, found.model, found.name,
                        existing.settings if existing else {})
        self._db.execute(
            "INSERT OR REPLACE INTO integration_devices (integration, device_id, host, model, name, settings)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (domain, device.device_id, host, device.model, device.name, json.dumps(device.settings)))
        if existing:
            integration.detach(device.device_id)
        integration.attach(device)
        return device, existing is None

    def remove(self, domain: str, device_id: str, actor: str) -> None:
        if not any(d.device_id == device_id for d in self.devices(domain)):
            raise KeyError(device_id)
        self._by_domain[domain].detach(device_id)
        self._db.execute("DELETE FROM integration_devices WHERE integration = ? AND device_id = ?",
                         (domain, device_id))
        self._credentials.delete_prefix(domain, f"{device_id}:", actor)
