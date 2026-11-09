"""Client address resolution behind trusted proxies, and the "home network only" range check."""

from collections.abc import Sequence
from ipaddress import IPv4Address, IPv6Address, ip_address, ip_network

IPAddress = IPv4Address | IPv6Address
UNKNOWN = ip_address("0.0.0.0")


def _parse(value: str) -> IPAddress | None:
    try:
        ip = ip_address(value.strip())
    except ValueError:
        return None
    if isinstance(ip, IPv6Address) and ip.ipv4_mapped:
        return ip.ipv4_mapped
    return ip


def _in(ip: IPAddress, ranges: Sequence[str]) -> bool:
    return any(ip in ip_network(r, strict=False) for r in ranges)


def resolve_client_ip(peer: str, forwarded_for: str | None, trusted: Sequence[str]) -> IPAddress:
    """The real client address. X-Forwarded-For is believed only from trusted proxies, read right to left."""
    peer_ip = _parse(peer)
    if peer_ip is None:
        return UNKNOWN
    if not forwarded_for or not _in(peer_ip, trusted):
        return peer_ip
    for hop in reversed(forwarded_for.split(",")):
        ip = _parse(hop)
        if ip is None:
            return UNKNOWN
        if not _in(ip, trusted):
            return ip
    return peer_ip


def is_local(ip: IPAddress, local_ranges: Sequence[str]) -> bool:
    return _in(ip, local_ranges)
