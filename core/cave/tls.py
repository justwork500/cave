"""CAVE's own HTTPS certificate: self-signed, made once on first run."""

import contextlib
import hashlib
import os
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

VALID_DAYS = 825  # the longest lifetime Apple platforms accept for a TLS certificate


def ensure_certificate(directory: Path, hostnames: list[str], ips: list[str]) -> tuple[Path, Path]:
    cert_path, key_path = directory / "cert.pem", directory / "key.pem"
    if cert_path.exists() and key_path.exists():
        return cert_path, key_path
    directory.mkdir(parents=True, exist_ok=True)
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostnames[0] if hostnames else "CAVE")])
    sans: list[x509.GeneralName] = [x509.DNSName(h) for h in dict.fromkeys(hostnames)]
    sans += [x509.IPAddress(ip_address(i)) for i in dict.fromkeys(ips)]
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=VALID_DAYS))
        .add_extension(x509.SubjectAlternativeName(sans), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(key, hashes.SHA256())
    )
    key_path.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    with contextlib.suppress(OSError):  # Windows ignores POSIX modes; Debian honours them
        os.chmod(key_path, 0o600)
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return cert_path, key_path


def fingerprint(cert_path: Path) -> str:
    der = x509.load_pem_x509_certificate(cert_path.read_bytes()).public_bytes(serialization.Encoding.DER)
    digest = hashlib.sha256(der).hexdigest().upper()
    return ":".join(digest[i : i + 2] for i in range(0, len(digest), 2))


def not_after(cert_path: Path) -> datetime:
    return x509.load_pem_x509_certificate(cert_path.read_bytes()).not_valid_after_utc
