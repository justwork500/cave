"""The KLAP client against a fake plug that implements the device's side of the protocol."""

import hashlib
import json
import os

import pytest

from cave.integrations.kasa.klap import KasaAuthError, KlapClient, Session, auth_hashes

GOOD = auth_hashes("sam@example.com", "pw")


def sha(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()


class FakePlug:
    def __init__(self, version: int = 2, auth: tuple[bytes, bytes] = GOOD) -> None:
        self.version, self.auth = version, auth[0] if version == 2 else auth[1]
        self.got: list[dict] = []
        self.handshakes = 0
        self.expire_next = False

    def __call__(self, host, path, body, cookie):
        if path == "/app/handshake1":
            self.handshakes += 1
            self.local, self.remote = body, os.urandom(16)
            proof = sha(self.local + self.remote + self.auth) if self.version == 2 else sha(self.local + self.auth)
            return 200, self.remote + proof, "TP_SESSIONID=abc;TIMEOUT=86400"
        assert cookie == "TP_SESSIONID=abc"
        if path == "/app/handshake2":
            want = sha(self.remote + self.local + self.auth) if self.version == 2 else sha(self.remote + self.auth)
            if body != want:
                return 403, b"", None
            self.session = Session(self.local, self.remote, self.auth)
            return 200, b"", None
        if self.expire_next:
            self.expire_next = False
            return 403, b"", None
        seq = int(path.split("seq=")[1])
        assert body[:32] == sha(self.session.sig + seq.to_bytes(4, "big", signed=True) + body[32:])
        self.got.append(json.loads(self.session.decrypt(seq, body)))
        self.session.seq = seq - 1
        return 200, self.session.encrypt(b'{"ok": true}')[1], None


@pytest.mark.parametrize("version", [1, 2])
def test_round_trip_on_both_handshake_versions(version):
    plug = FakePlug(version)
    client = KlapClient("h", GOOD, plug)
    assert client.request({"a": 1}) == {"ok": True}
    assert client.request({"a": 2}) == {"ok": True}
    assert plug.got == [{"a": 1}, {"a": 2}]
    assert plug.handshakes == 1


def test_wrong_sign_in_is_its_own_error():
    client = KlapClient("h", auth_hashes("sam@example.com", "wrong"), FakePlug())
    with pytest.raises(KasaAuthError):
        client.request({})


def test_an_expired_session_shakes_hands_again():
    plug = FakePlug()
    client = KlapClient("h", GOOD, plug)
    client.request({"a": 1})
    plug.expire_next = True
    assert client.request({"a": 2}) == {"ok": True}
    assert plug.handshakes == 2
