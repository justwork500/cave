"""A tablet stand-in: a P-256 key that signs like WebCrypto (IEEE P1363, raw r||s)."""

import base64

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature


class FakeTablet:
    def __init__(self) -> None:
        self.key = ec.generate_private_key(ec.SECP256R1())

    @property
    def spki_der(self) -> bytes:
        return self.key.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )

    @property
    def spki_b64(self) -> str:
        return base64.b64encode(self.spki_der).decode()

    def sign(self, screen_id: str, nonce: str) -> str:
        der = self.key.sign(f"cave-screen-auth:{screen_id}:{nonce}".encode(), ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der)
        return base64.b64encode(r.to_bytes(32, "big") + s.to_bytes(32, "big")).decode()


def spki_b64_of(public_key: ec.EllipticCurvePublicKey | rsa.RSAPublicKey) -> str:
    der = public_key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return base64.b64encode(der).decode()
