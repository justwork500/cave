"""Kasa devices as CAVE switches: the ones an Admin added are polled, and take commands through KLAP."""

import asyncio
import base64
import binascii
import logging
from collections.abc import Callable, Sequence
from typing import Any, Protocol

from cave.db import Database
from cave.integrations.kasa.discovery import Found, discover, hosts_in
from cave.integrations.kasa.klap import KasaAuthError, KasaError, KlapClient, auth_hashes
from cave.state import Entity, StateMachine

log = logging.getLogger(__name__)
POLL_SECONDS = 30.0
NOT_RESPONDING = "This device isn't responding."


class Client(Protocol):
    def request(self, payload: dict[str, Any]) -> dict[str, Any]: ...


def read(client: Client, kind: str) -> tuple[bool, str]:
    """(on, the name set in the Kasa app)."""
    try:
        if kind == "iot":
            info = client.request({"system": {"get_sysinfo": {}}})["system"]["get_sysinfo"]
            return bool(info["relay_state"]), str(info["alias"])
        reply = client.request({"method": "get_device_info"})
        if reply.get("error_code"):
            raise KasaError(f"error {reply['error_code']}")
        info = reply["result"]
        return bool(info["device_on"]), base64.b64decode(info["nickname"]).decode()
    except (KeyError, TypeError, ValueError, binascii.Error) as e:
        raise KasaError("unexpected reply") from e


def write(client: Client, kind: str, on: bool) -> None:
    if kind == "iot":
        reply = client.request({"system": {"set_relay_state": {"state": int(on)}}})
        code = reply.get("system", {}).get("set_relay_state", {}).get("err_code")
    else:
        code = client.request({"method": "set_device_info", "params": {"device_on": on}}).get("error_code")
    if code:
        raise KasaError(f"error {code}")


def entity_id(mac: str) -> str:
    return f"switch.kasa_{mac}"


class KasaService:
    def __init__(self, db: Database, states: StateMachine) -> None:
        self.db, self.states = db, states
        self.client: Callable[[str, tuple[bytes, bytes]], Client] = KlapClient
        self.discover: Callable[[Sequence[str]], list[Found]] = discover
        self._clients: dict[str, Client] = {}
        self._found: dict[str, Found] = {}

    def _hashes(self) -> tuple[bytes, bytes] | None:
        row = self.db.execute("SELECT hash_v2, hash_v1 FROM kasa_login").fetchone()
        return (row["hash_v2"], row["hash_v1"]) if row else None

    def _client_for(self, host: str) -> Client:
        hashes = self._hashes()
        if hashes is None:
            raise KasaAuthError("not signed in")
        if host not in self._clients:
            self._clients[host] = self.client(host, hashes)
        return self._clients[host]

    def _rows(self) -> list[dict[str, str]]:
        return [dict(r) for r in self.db.execute("SELECT mac, host, model, kind, name FROM kasa_devices").fetchall()]

    def _register(self, mac: str, name: str) -> None:
        self.states.register(Entity(entity_id(mac), name, None, "switch"))
        self.states.set_entity_handler(entity_id(mac), self._handler)

    def load(self) -> None:
        for row in self._rows():
            self._register(row["mac"], row["name"])

    def set_login(self, username: str, password: str) -> None:
        v2, v1 = auth_hashes(username, password)
        self.db.execute("INSERT INTO kasa_login (id, hash_v2, hash_v1) VALUES (1, ?, ?) ON CONFLICT(id) DO UPDATE "
                        "SET hash_v2=excluded.hash_v2, hash_v1=excluded.hash_v1", (v2, v1))
        self._clients.clear()

    async def scan(self, ranges: Sequence[str]) -> dict[str, Any]:
        """What's on the network, plus what's already added even if it didn't answer."""
        seen = await asyncio.to_thread(self.discover, hosts_in(ranges))
        self._found = {d.mac: d for d in seen}
        rows = {r["mac"]: r for r in self._rows()}
        for d in seen:
            row = rows.get(d.mac)
            if row is not None and row["host"] != d.host:  # DHCP moved it
                self.db.execute("UPDATE kasa_devices SET host=? WHERE mac=?", (d.host, d.mac))
                row["host"] = d.host
        signed_in = self._hashes() is not None
        names = await asyncio.gather(*(self._name(d) for d in seen)) if signed_in else [None] * len(seen)
        refused = any(n is False for n in names)
        answered = any(isinstance(n, str) for n in names)
        devices = [{"mac": d.mac, "host": d.host, "model": d.model, "added": d.mac in rows,
                    "name": n if isinstance(n, str) else None} for d, n in zip(seen, names, strict=True)]
        devices += [{"mac": r["mac"], "host": r["host"], "model": r["model"], "added": True, "name": r["name"]}
                    for r in rows.values() if r["mac"] not in self._found]
        return {"signed_in": signed_in, "login_ok": (answered or not refused) if seen and signed_in else None,
                "devices": devices}

    async def _name(self, d: Found) -> str | bool | None:
        """The device's name; False when it refused the sign-in, None when it couldn't say."""
        try:
            return (await asyncio.to_thread(read, self._client_for(d.host), d.kind))[1]
        except KasaAuthError:
            return False
        except KasaError:
            return None

    async def add(self, mac: str) -> dict[str, str]:
        d = self._found[mac]
        on, name = await asyncio.to_thread(read, self._client_for(d.host), d.kind)
        self.db.execute("INSERT OR REPLACE INTO kasa_devices (mac, host, model, kind, name) VALUES (?, ?, ?, ?, ?)",
                        (mac, d.host, d.model, d.kind, name))
        self._register(mac, name)
        self.states.set(entity_id(mac), "on" if on else "off")
        return {"mac": mac, "host": d.host, "model": d.model, "name": name}

    def remove(self, mac: str) -> dict[str, str] | None:
        row = next((r for r in self._rows() if r["mac"] == mac), None)
        if row is not None:
            self.db.execute("DELETE FROM kasa_devices WHERE mac=?", (mac,))
            self.states.remove(entity_id(mac))
        return row

    async def _poll_one(self, row: dict[str, str]) -> None:
        try:
            on, _ = await asyncio.to_thread(read, self._client_for(row["host"]), row["kind"])
            value = "on" if on else "off"
        except KasaError as e:
            log.warning("Kasa device %s: %s", row["mac"], e)
            value = "unavailable"
        if self.states.entity(entity_id(row["mac"])) is not None:  # it may have been removed meanwhile
            self.states.set(entity_id(row["mac"]), value)

    async def poll(self) -> None:
        await asyncio.gather(*(self._poll_one(r) for r in self._rows()))

    async def run(self) -> None:
        # shortcut: a device that moves address reads unavailable until the next scan; rescan here if that bites
        while True:
            await self.poll()
            await asyncio.sleep(POLL_SECONDS)

    async def _handler(self, entity: str, command: str, args: dict[str, Any]) -> None:
        row = next((r for r in self._rows() if entity_id(r["mac"]) == entity), None)
        if row is None:
            raise KeyError(entity)
        if command == "toggle":
            current = self.states.get(entity)
            command = "turn_off" if current is not None and current.value == "on" else "turn_on"
        if command not in ("turn_on", "turn_off"):
            raise ValueError(f"A Kasa device can't {command}.")
        on = command == "turn_on"
        try:
            await asyncio.to_thread(write, self._client_for(row["host"]), row["kind"], on)
        except KasaError as e:
            raise ValueError(NOT_RESPONDING) from e
        self.states.set(entity, "on" if on else "off")
