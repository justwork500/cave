#!/usr/bin/env python3
"""End-to-end check of a running CAVE stack, run from the repository root after deploy/install.sh.

Standard library only. Prints one line per check and stops at the first failure (exit 1).
  python3 deploy/smoke.py                   first run: sets up an owner and checks the stack
  python3 deploy/smoke.py --after-restart   the owner from the first run can still sign in
The owner's test credentials are kept in --state (default: data/smoke-state.json, readable by you only).
"""

import argparse
import base64
import hashlib
import hmac
import http.cookiejar
import json
import os
import re
import secrets
import socket
import ssl
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

AUTOMATION = """automation:
  id: smoke
  name: Smoke test
  triggers:
    - type: time
      at: "07:00"
  actions:
    - type: notify
      message: "Smoke test"
"""


class Failed(Exception):
    pass


def check(name: str, ok: bool, why: str = "") -> None:
    if not ok:
        raise Failed(f"{name}: {why}" if why else name)
    print(f"ok    {name}")


class Client:
    """HTTPS with a cookie jar. The certificate is CAVE's own self-signed one on this machine, so it isn't checked."""

    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        context = ssl.create_default_context()
        context.check_hostname, context.verify_mode = False, ssl.CERT_NONE
        self.opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context),
                                                  urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, method: str, path: str, body: Any = None) -> tuple[int, dict[str, str], Any]:
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"content-type": "application/json"} if data else {})
        try:
            with self.opener.open(req, timeout=10) as r:
                raw, status, headers = r.read(), r.status, dict(r.headers)
        except urllib.error.HTTPError as e:
            raw, status, headers = e.read(), e.code, dict(e.headers)
        except OSError as e:
            raise Failed(f"{method} {path}: CAVE isn't answering at {self.base} ({e})") from e
        try:
            return status, {k.lower(): v for k, v in headers.items()}, json.loads(raw) if raw else None
        except ValueError:
            return status, {k.lower(): v for k, v in headers.items()}, raw.decode(errors="replace")


def totp(secret: str, at: float | None = None) -> str:
    """RFC 6238: 30-second steps, SHA-1, 6 digits (what CAVE's authenticator setup uses)."""
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", int((at or time.time()) // 30)), hashlib.sha1).digest()
    offset = digest[-1] & 15
    return f"{(struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1_000_000:06d}"


def sh(*cmd: str) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


def read_secret(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except PermissionError:  # 0400 and owned by the container's uid
        return sh("sudo", "cat", path).strip()


def sign_in(c: Client, state: dict[str, str]) -> None:
    status, _, body = c.call("POST", "/api/v1/auth/login", {"username": state["username"], "password": state["password"]})
    check("owner signs in with a password", status == 200 and body == {"mfa_required": True}, f"{status} {body}")
    status, _, body = c.call("POST", "/api/v1/auth/mfa", {"code": totp(state["totp"])})
    check("and the authenticator code", status == 200, f"{status} {body}")


def first_run(c: Client, state_file: Path) -> None:
    status, _, body = c.call("GET", "/api/v1/health")
    check("health", status == 200 and body == {"status": "ok"}, f"{status} {body}")
    status, headers, _ = c.call("GET", "/")
    check("console page has the CSP", "script-src 'self'" in headers.get("content-security-policy", ""))
    _, _, page = c.call("GET", "/enroll")
    check("enroll page has no inline script", isinstance(page, str) and re.search(r"<script(?![^>]*\bsrc=)[^>]*>", page) is None)

    found = re.findall(r"setup code: (\S+)", sh("docker", "compose", "logs", "cave"))
    check("setup code printed", bool(found))
    state = {"username": "smoke-owner", "password": secrets.token_urlsafe(18)}
    status, _, body = c.call("POST", "/api/v1/setup", {"code": found[-1], "username": state["username"],
                                                        "password": state["password"], "display_name": "Smoke"})
    check("owner created with the setup code", status == 200 and "provisioning_uri" in body, f"{status} {body}")
    state["totp"] = urllib.parse.parse_qs(urllib.parse.urlparse(body["provisioning_uri"]).query)["secret"][0]
    status, _, body = c.call("POST", "/api/v1/auth/mfa", {"code": totp(state["totp"])})
    check("authenticator proven", status == 200, f"{status} {body}")
    state_file.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(state_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(state, f)

    status, _, body = c.call("PUT", "/api/v1/automations/smoke", {"yaml": AUTOMATION})
    saved = Path("config/automations/smoke.yaml")
    check("saving a file through the API works (ownership)", status == 200 and saved.exists(), f"{status} {body}")

    with socket.socket() as s:
        s.settimeout(3)
        refused = s.connect_ex(("127.0.0.1", 8099)) != 0
    check("script runner not reachable from the host", refused)

    connect = bytes([0x10, 17, 0, 4]) + b"MQTT" + bytes([4, 2, 0, 60, 0, 5]) + b"smoke"
    with socket.create_connection(("127.0.0.1", 1883), timeout=5) as s:
        s.sendall(connect)
        connack = s.recv(4)
    check("Mosquitto refuses anonymous clients", connack[:1] == b"\x20" and connack[3:4] == b"\x05", connack.hex())

    rendered = sh("docker", "compose", "config") + sh("docker", "inspect", sh("docker", "compose", "ps", "-q", "cave").strip())
    leaked = [name for name in ("secrets/runner_token", "secrets/mqtt_password") if read_secret(name) in rendered]
    check("no secret in compose config or docker inspect", not leaked, ", ".join(leaked))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="https://127.0.0.1:8443")
    parser.add_argument("--after-restart", action="store_true")
    parser.add_argument("--state", type=Path, default=Path("data/smoke-state.json"))
    args = parser.parse_args()
    c = Client(args.url)
    try:
        if args.after_restart:
            sign_in(c, json.loads(args.state.read_text(encoding="utf-8")))
        else:
            first_run(c, args.state)
    except (Failed, subprocess.CalledProcessError, OSError, KeyError) as e:
        print(f"FAIL  {e}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
