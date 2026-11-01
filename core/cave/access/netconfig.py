"""Local address ranges and trusted proxies, kept in the database (System > Networks)."""

import socket
from dataclasses import dataclass
from ipaddress import ip_address, ip_network

from cave import audit
from cave.db import Database
from cave.settings import Settings


@dataclass(frozen=True)
class NetConfig:
    local_ranges: tuple[str, ...]
    trusted_proxies: tuple[str, ...]


class InvalidRange(ValueError):
    def __init__(self, value: str) -> None:
        super().__init__(f"Not a valid address range: {value}")
        self.value = value


def _normalize(values: list[str]) -> tuple[str, ...]:
    out: list[str] = []
    for v in values:
        try:
            out.append(str(ip_network(v.strip(), strict=False)))
        except ValueError as e:
            raise InvalidRange(v) from e
    return tuple(dict.fromkeys(out))


def load(db: Database) -> NetConfig:
    rows = db.execute("SELECT cidr, kind FROM network_ranges ORDER BY rowid").fetchall()
    return NetConfig(
        tuple(r["cidr"] for r in rows if r["kind"] == "local"),
        tuple(r["cidr"] for r in rows if r["kind"] == "trusted_proxy"),
    )


def save(db: Database, actor: str, local_ranges: list[str], trusted_proxies: list[str]) -> NetConfig:
    new = NetConfig(_normalize(local_ranges), _normalize(trusted_proxies))
    old = load(db)
    with db.transaction() as conn:
        conn.execute("DELETE FROM network_ranges")
        conn.executemany(
            "INSERT INTO network_ranges (cidr, kind) VALUES (?, ?)",
            [(c, "local") for c in new.local_ranges] + [(c, "trusted_proxy") for c in new.trusted_proxies],
        )
    audit.record(
        db,
        actor,
        "network.update",
        "system:networks",
        {"local_ranges": list(old.local_ranges), "trusted_proxies": list(old.trusted_proxies)},
        {"local_ranges": list(new.local_ranges), "trusted_proxies": list(new.trusted_proxies)},
    )
    return new


def host_ipv4() -> str | None:
    # shortcut: finds the one interface used for outbound traffic; Admins add other ranges by hand
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("192.0.2.1", 9))  # TEST-NET-1: a UDP connect sends no packets, it only picks a route
            return str(s.getsockname()[0])
        except OSError:
            return None


def detect_local_ranges() -> list[str]:
    ip = host_ipv4()
    if ip is None or not ip_address(ip).is_private:
        return []
    return [str(ip_network(f"{ip}/24", strict=False))]


def seed(db: Database, settings: Settings) -> None:
    """First run only: never overwrites what an Admin has saved."""
    if db.execute("SELECT count(*) FROM network_ranges").fetchone()[0]:
        return
    detected = detect_local_ranges() if settings.detect_ranges else []  # none: Local only fails closed
    save(db, "system", settings.local_ranges or detected, settings.trusted_proxies)
