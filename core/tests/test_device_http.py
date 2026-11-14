import asyncio
import json
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from cave.integrations import http as dev


class _Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: bytes, ctype: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.startswith("/api/s3cr3t-key"):
            self._send(500, b"{}")
        elif self.path == "/html":
            self._send(200, b"<html>login</html>", "text/html")
        elif self.path == "/big":
            self._send(200, json.dumps({"x": "y" * 500}).encode())
        elif self.path == "/slow":
            time.sleep(1)
            self._send(200, b"{}")
        else:
            self._send(200, b'{"on": true}')

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers["Content-Length"]))
        self._send(200, json.dumps({"got": json.loads(body)}).encode())

    def log_message(self, format: str, *args: Any) -> None:
        pass


@pytest.fixture()
def port() -> Iterator[int]:
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1]
    server.shutdown()
    server.server_close()


def test_get_and_post_json(port: int) -> None:
    assert asyncio.run(dev.request("GET", "127.0.0.1", "/x", port=port)) == {"on": True}
    assert asyncio.run(dev.request("POST", "127.0.0.1", "/x", port=port, body={"a": 1})) == {"got": {"a": 1}}


def test_errors_never_show_the_path(port: int, caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(dev.DeviceError) as e:
        asyncio.run(dev.request("GET", "127.0.0.1", "/api/s3cr3t-key/lights?password=hunter2", port=port))
    assert str(e.value) == "HTTP 500"
    for secret in ("s3cr3t-key", "hunter2"):
        assert secret not in str(e.value)
        assert secret not in caplog.text


def test_not_json_and_too_large(port: int, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(dev.DeviceError, match="not JSON"):
        asyncio.run(dev.request("GET", "127.0.0.1", "/html", port=port))
    monkeypatch.setattr(dev, "MAX_BYTES", 100)
    with pytest.raises(dev.DeviceError, match="too large"):
        asyncio.run(dev.request("GET", "127.0.0.1", "/big", port=port))


def test_timeout(port: int, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dev, "TIMEOUT_SECONDS", 0.2)
    start = time.monotonic()
    with pytest.raises(dev.DeviceError, match="no answer"):
        asyncio.run(dev.request("GET", "127.0.0.1", "/slow", port=port))
    assert time.monotonic() - start < 1
