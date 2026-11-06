"""Finding Kasa devices. Each address is asked directly: CAVE runs on a Docker bridge, where broadcasts stop."""

import ipaddress
import json
import re
import socket
import time
from collections.abc import Sequence
from dataclasses import dataclass

PORT = 20002
ASK = bytes.fromhex("020000010000000000000000463cb5d3")
WAIT = 3.0
MIN_PREFIX = 22  # shortcut: wider ranges aren't scanned, add a range picker if a home network ever needs one
MAC = re.compile(r"^[0-9a-f]{12}$")


@dataclass(frozen=True)
class Found:
    mac: str
    host: str
    model: str
    kind: str  # "iot" or "smart": the two message formats


def hosts_in(ranges: Sequence[str]) -> list[str]:
    out: list[str] = []
    for cidr in ranges:
        network = ipaddress.ip_network(cidr, strict=False)
        if network.version == 4 and network.prefixlen >= MIN_PREFIX and not network.is_loopback:
            out.extend(str(h) for h in network.hosts())
    return out


def parse_reply(data: bytes, host: str) -> Found | None:
    """Anyone on the LAN can answer, so nothing here is taken on trust. host is where the reply really came from."""
    try:
        result = json.loads(data[16:])["result"]
        mac = str(result["mac"]).replace("-", "").replace(":", "").lower()
        model, kind = str(result["device_model"])[:40], str(result["device_type"]).split(".")[0]
        # shortcut: only KLAP devices are offered; older and Tapo-only encryption would need their own client
        scheme = result["mgt_encrypt_schm"]["encrypt_type"]
    except (ValueError, KeyError, TypeError):
        return None
    if scheme != "KLAP" or not MAC.fullmatch(mac) or kind not in ("IOT", "SMART"):
        return None
    return Found(mac, host, model, kind.lower())


def discover(hosts: Sequence[str]) -> list[Found]:
    found: dict[str, Found] = {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(0.3)
        for host in hosts:
            try:
                sock.sendto(ASK, (host, PORT))
            except OSError:
                continue  # one unreachable address doesn't end the scan
        end = time.monotonic() + WAIT
        while time.monotonic() < end:
            try:
                data, address = sock.recvfrom(8192)
            except OSError:  # includes the timeout: keep listening until WAIT is up
                continue
            if address[0] in hosts and (device := parse_reply(data, address[0])) is not None:
                found[device.mac] = device
    return sorted(found.values(), key=lambda d: d.host)
