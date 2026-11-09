"""The registry every Phase 2 integration plugs into: probe, pair, attach, detach, run."""

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from cave import audit
from cave.credentials import Credentials
from cave.db import Database

log = logging.getLogger(__name__)
Pairing = Literal["none", "password", "key", "pin", "button"]
PROBE_SECONDS = 5.0
PAIR_SECONDS = 30.0


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
    """What an integration provides.

    - `pair(host, None)` may start pairing when the PIN is only shown afterwards (Apple TV): it raises
      `PairingError("Type the PIN now shown on the TV.")` and keeps the pairing session for that host; the
      next `pair(host, pin)` completes it. The panel supports this (Add stays enabled with an empty box).
    - `run()` must recover internally: catch per-device errors and keep going so devices come back on their
      own. The registry only logs a `run()` that escapes.
    - `attach` and `detach` may be called for ids the integration doesn't know and must tolerate that
      (the registry also guards them).
    """

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
        for device in self.devices(integration.domain):
            try:
                integration.attach(device)
            except Exception:
                log.exception("Could not attach %s device %s; skipping it.", integration.domain, device.device_id)

    def get(self, domain: str) -> Integration | None:
        return self._by_domain.get(domain)

    def all(self) -> list[Integration]:
        return list(self._by_domain.values())

    def devices(self, domain: str) -> list[Device]:
        rows = self._db.execute("SELECT * FROM integration_devices WHERE integration = ? ORDER BY device_id",
                                (domain,)).fetchall()
        return [Device(r["integration"], r["device_id"], r["host"], r["model"], r["name"],
                       json.loads(r["settings"])) for r in rows]

    async def run(self) -> None:
        await asyncio.gather(*(self._run_one(i) for i in self.all()))

    @staticmethod
    async def _run_one(integration: Integration) -> None:
        try:
            await integration.run()
        except Exception:  # one integration crashing must not stop the others or shutdown
            log.exception("The %s integration stopped unexpectedly.", integration.domain)

    async def probe(self, domain: str, host: str) -> Found | None:
        try:
            return await asyncio.wait_for(self._by_domain[domain].probe(host), PROBE_SECONDS)
        except TimeoutError:
            return None
        except Exception as e:  # noqa: BLE001 - type name only: the text may hold URLs or secrets
            log.warning("Probing %s at %s failed (%s).", domain, host, type(e).__name__)
            return None

    async def add(self, domain: str, host: str, secret: str | None, actor: str) -> tuple[Device, bool]:
        integration = self._by_domain[domain]
        try:
            found, creds = await asyncio.wait_for(integration.pair(host, secret), PAIR_SECONDS)
        except PairingError:
            raise
        except (TimeoutError, OSError):
            raise PairingError("The device didn't answer. Check it's on and try again.") from None
        except Exception as e:  # noqa: BLE001 - type name only: the text may hold secrets
            log.warning("Pairing %s at %s failed (%s).", domain, host, type(e).__name__)
            raise PairingError("Pairing failed. Check the device and try again.") from None
        if ":" in found.device_id:  # would collide with another device's credential prefix
            raise PairingError("This device reported an id CAVE can't use.")
        for key, value in creds.items():
            self._credentials.set(domain, f"{found.device_id}:{key}", value, actor)
        existing = next((d for d in self.devices(domain) if d.device_id == found.device_id), None)
        device = Device(domain, found.device_id, host, found.model, found.name,
                        existing.settings if existing else {})
        self._db.execute(
            "INSERT OR REPLACE INTO integration_devices (integration, device_id, host, model, name, settings)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (domain, device.device_id, host, device.model, device.name, json.dumps(device.settings)))
        shown = {"device_id": device.device_id, "host": host, "model": device.model, "name": device.name}
        target = f"integration:{domain}:{device.device_id}"
        if existing:
            audit.record(self._db, actor, "integration.update", target, {"host": existing.host}, {"host": host})
            self._detach(integration, device.device_id)
        else:
            audit.record(self._db, actor, "integration.add", target, None, shown)
        try:
            integration.attach(device)
        except Exception:  # the device is saved; register() retries it at the next start
            log.exception("Could not attach %s device %s.", domain, device.device_id)
        return device, existing is None

    @staticmethod
    def _detach(integration: Integration, device_id: str) -> None:
        try:
            integration.detach(device_id)
        except Exception:  # e.g. a device that never attached; it must still be removable
            log.exception("Could not detach %s device %s.", integration.domain, device_id)

    def remove(self, domain: str, device_id: str, actor: str) -> None:
        if not any(d.device_id == device_id for d in self.devices(domain)):
            raise KeyError(device_id)
        self._detach(self._by_domain[domain], device_id)
        self._db.execute("DELETE FROM integration_devices WHERE integration = ? AND device_id = ?",
                         (domain, device_id))
        self._credentials.delete_prefix(domain, f"{device_id}:", actor)
