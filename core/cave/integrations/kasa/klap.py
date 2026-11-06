"""TP-Link's local KLAP protocol: the encrypted HTTP that current Kasa plugs and switches speak on the LAN.

Written for CAVE from the protocol; no python-kasa code, which is GPL-3.0 (CAVE is Apache-2.0).
"""

import hashlib
import http.client
import json
import os
import threading
from collections.abc import Callable
from typing import Any

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

TIMEOUT = 5.0
# (host, path, body, cookie) -> (status, body, Set-Cookie)
Post = Callable[[str, str, bytes, str | None], tuple[int, bytes, str | None]]


class KasaError(Exception):
    """The device can't be reached or answered badly."""


class KasaAuthError(KasaError):
    """The device didn't accept the TP-Link sign-in."""


def _sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def _sha1(data: bytes) -> bytes:
    return hashlib.sha1(data, usedforsecurity=False).digest()


def _md5(data: bytes) -> bytes:
    return hashlib.md5(data, usedforsecurity=False).digest()


def auth_hashes(username: str, password: str) -> tuple[bytes, bytes]:
    """(v2, v1): devices use one or the other, and only the handshake tells which."""
    u, p = username.encode(), password.encode()
    return _sha256(_sha1(u) + _sha1(p)), _md5(_md5(u) + _md5(p))


def http_post(host: str, path: str, body: bytes, cookie: str | None) -> tuple[int, bytes, str | None]:
    conn = http.client.HTTPConnection(host, 80, timeout=TIMEOUT)
    try:
        conn.request("POST", path, body, {"Cookie": cookie} if cookie else {})
        response = conn.getresponse()
        return response.status, response.read(), response.getheader("Set-Cookie")
    finally:
        conn.close()


class Session:
    """The keys both sides derive from the two seeds and the sign-in hash."""

    def __init__(self, local: bytes, remote: bytes, auth: bytes) -> None:
        seeds = local + remote + auth
        self.key = _sha256(b"lsk" + seeds)[:16]
        iv = _sha256(b"iv" + seeds)
        self.iv, self.seq = iv[:12], int.from_bytes(iv[-4:], "big", signed=True)
        self.sig = _sha256(b"ldk" + seeds)[:28]

    def _cipher(self, seq: int) -> Cipher[modes.CBC]:
        return Cipher(algorithms.AES(self.key), modes.CBC(self.iv + seq.to_bytes(4, "big", signed=True)))

    def encrypt(self, plain: bytes) -> tuple[int, bytes]:
        self.seq += 1
        padder = padding.PKCS7(128).padder()
        encryptor = self._cipher(self.seq).encryptor()
        data = encryptor.update(padder.update(plain) + padder.finalize()) + encryptor.finalize()
        return self.seq, _sha256(self.sig + self.seq.to_bytes(4, "big", signed=True) + data) + data

    def decrypt(self, seq: int, body: bytes) -> bytes:
        decryptor = self._cipher(seq).decryptor()
        unpadder = padding.PKCS7(128).unpadder()
        padded = decryptor.update(body[32:]) + decryptor.finalize()
        return unpadder.update(padded) + unpadder.finalize()


class KlapClient:
    def __init__(self, host: str, hashes: tuple[bytes, bytes], post: Post = http_post) -> None:
        self.host, self.hashes, self.post = host, hashes, post
        self._session: Session | None = None
        self._cookie: str | None = None
        self._lock = threading.Lock()  # each request takes the next sequence number

    def _handshake(self) -> None:
        local = os.urandom(16)
        status, body, cookie = self.post(self.host, "/app/handshake1", local, None)
        if status != 200 or len(body) != 48:
            raise KasaError(f"handshake refused ({status})")
        remote, server_hash = body[:16], body[16:]
        v2, v1 = self.hashes
        if _sha256(local + remote + v2) == server_hash:
            auth, proof = v2, _sha256(remote + local + v2)
        elif _sha256(local + v1) == server_hash:
            auth, proof = v1, _sha256(remote + v1)
        else:
            raise KasaAuthError("sign-in not accepted")
        session_cookie = cookie.split(";")[0] if cookie else None
        status, _, _ = self.post(self.host, "/app/handshake2", proof, session_cookie)
        if status != 200:
            raise KasaAuthError(f"sign-in not accepted ({status})")
        self._session, self._cookie = Session(local, remote, auth), session_cookie

    def _send(self, plain: bytes) -> bytes:
        if self._session is None:
            self._handshake()
        assert self._session is not None
        seq, body = self._session.encrypt(plain)
        status, reply, _ = self.post(self.host, f"/app/request?seq={seq}", body, self._cookie)
        if status != 200:
            raise KasaError(f"request refused ({status})")
        return self._session.decrypt(seq, reply)

    def request(self, payload: dict[str, Any]) -> dict[str, Any]:
        plain = json.dumps(payload).encode()
        with self._lock:
            try:
                reply = self._send(plain)
            except KasaAuthError:
                raise
            except (KasaError, ValueError, OSError):  # sessions expire and plugs restart: one fresh try
                self._session = None
                try:
                    reply = self._send(plain)
                except (ValueError, OSError) as e:
                    self._session = None
                    raise KasaError(str(e)) from e
        try:
            out = json.loads(reply)
        except ValueError as e:
            raise KasaError("unreadable reply") from e
        if not isinstance(out, dict):
            raise KasaError("unreadable reply")
        return out
