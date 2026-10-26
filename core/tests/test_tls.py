import hashlib
import re
from ipaddress import ip_address

from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding

from cave import tls


def test_creates_once_and_reuses(tmp_path):
    cert, key = tls.ensure_certificate(tmp_path, ["cave.local"], ["192.168.1.10"])
    mtime = cert.stat().st_mtime_ns
    assert tls.ensure_certificate(tmp_path, ["other"], []) == (cert, key)
    assert cert.stat().st_mtime_ns == mtime and key.exists()


def test_sans_include_hostnames_and_ips(tmp_path):
    cert, _ = tls.ensure_certificate(tmp_path, ["cave.local", "localhost"], ["192.168.1.10"])
    c = x509.load_pem_x509_certificate(cert.read_bytes())
    san = c.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert "cave.local" in san.get_values_for_type(x509.DNSName)
    assert ip_address("192.168.1.10") in san.get_values_for_type(x509.IPAddress)


def test_fingerprint_format(tmp_path):
    cert, _ = tls.ensure_certificate(tmp_path, ["cave.local"], [])
    fp = tls.fingerprint(cert)
    assert re.fullmatch(r"([0-9A-F]{2}:){31}[0-9A-F]{2}", fp)
    der = x509.load_pem_x509_certificate(cert.read_bytes()).public_bytes(Encoding.DER)
    h = hashlib.sha256(der).hexdigest().upper()
    assert fp == ":".join(h[i : i + 2] for i in range(0, 64, 2))
