"""Settings, secrets and certificate names from the environment, for running in a container."""

import os
import re
import socket
from collections.abc import Mapping
from ipaddress import ip_address, ip_network
from pathlib import Path

from cave.access import netconfig
from cave.settings import Settings


def env_secret(name: str, environ: Mapping[str, str] = os.environ) -> str | None:
    """{name}_FILE (a Compose secret) wins over {name}. Errors name the variable, never the contents."""
    path = environ.get(f"{name}_FILE")
    if path:
        try:
            value = Path(path).read_text(encoding="utf-8").removesuffix("\n")
        except OSError as e:
            raise SystemExit(f"{name}_FILE points at {path}, which can't be read ({e.strerror}).") from e
    else:
        value = environ.get(name, "")
    return value or None


def _words(value: str) -> list[str]:
    return [w for w in re.split(r"[\s,]+", value) if w]


def _ranges(name: str, environ: Mapping[str, str]) -> list[str]:
    out = []
    for w in _words(environ.get(name, "")):
        try:
            out.append(str(ip_network(w, strict=False)))
        except ValueError as e:
            raise SystemExit(f"{name} has {w!r}, which isn't a network range like 192.168.1.0/24.") from e
    return out


def settings_from_env(data: Path, config: Path, environ: Mapping[str, str] = os.environ) -> Settings:
    """Empty ranges keep first-run detection (netconfig.seed), except in a container (CAVE_IN_CONTAINER=1, set by
    the image), where detection would find Docker's network. After the first run the database decides."""
    return Settings(db_path=data / "cave.db", config_dir=config,
                    local_ranges=_ranges("CAVE_LOCAL_RANGES", environ),
                    trusted_proxies=_ranges("CAVE_TRUSTED_PROXIES", environ),
                    detect_ranges=environ.get("CAVE_IN_CONTAINER") != "1")


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(i for i in items if i))


def cert_names(environ: Mapping[str, str] = os.environ) -> tuple[list[str], list[str]]:
    """Hostnames and IPs for the self-signed certificate. In a container the host's own can't be detected."""
    names = _words(environ.get("CAVE_HOSTNAMES", "")) or [socket.gethostname()]
    ips = _words(environ.get("CAVE_HOST_IPS", "")) or [netconfig.host_ipv4() or ""]
    for ip in ips:
        try:
            ip_address(ip)
        except ValueError as e:
            if ip:
                raise SystemExit(f"CAVE_HOST_IPS has {ip!r}, which isn't an IP address.") from e
    return _unique([*names, "localhost"]), _unique([*ips, "127.0.0.1"])


def cert_paths(cert: Path | None, key: Path | None, environ: Mapping[str, str] = os.environ
               ) -> tuple[Path, Path] | None:
    """Your own certificate from --cert/--key, else CAVE_CERT/CAVE_KEY; None means CAVE makes one."""
    cert = cert or (Path(c) if (c := environ.get("CAVE_CERT")) else None)
    key = key or (Path(k) if (k := environ.get("CAVE_KEY")) else None)
    if bool(cert) != bool(key):
        raise SystemExit("--cert and --key (or CAVE_CERT and CAVE_KEY) go together.")
    return (cert, key) if cert and key else None
