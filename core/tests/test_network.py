from cave.access.network import is_local, resolve_client_ip


def test_spoofed_xff_from_untrusted_peer_ignored():  # Review Focus 1
    assert str(resolve_client_ip("203.0.113.9", "192.168.1.5", ["192.168.1.1/32"])) == "203.0.113.9"


def test_xff_ignored_when_no_trusted_proxies():
    assert str(resolve_client_ip("203.0.113.9", "192.168.1.5", [])) == "203.0.113.9"


def test_xff_from_trusted_proxy_used():
    assert str(resolve_client_ip("192.168.1.1", "203.0.113.9, 192.168.1.1", ["192.168.1.1/32"])) == "203.0.113.9"


def test_xff_left_spoof_through_trusted_proxy_ignored():
    # client prepends a fake LAN address; the proxy appends the real one
    assert str(resolve_client_ip("192.168.1.1", "192.168.1.50, 203.0.113.9", ["192.168.1.1/32"])) == "203.0.113.9"


def test_garbage_xff_fails_closed():
    # never fall back to the (local) proxy address: that would make a broken header look local
    ip = resolve_client_ip("192.168.1.1", "not-an-ip", ["192.168.1.1/32"])
    assert str(ip) == "0.0.0.0" and not is_local(ip, ["192.168.1.0/24"])


def test_ipv4_mapped_ipv6_is_local():  # Review Focus 2
    assert is_local(resolve_client_ip("::ffff:192.168.1.5", None, []), ["192.168.1.0/24"])


def test_wan_not_local():
    assert not is_local(resolve_client_ip("203.0.113.9", None, []), ["192.168.1.0/24"])
