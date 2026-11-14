import asyncio
import json
from typing import Any, ClassVar

import pytest

from cave.integrations import http as dev


class FakeConnection:
    """Stands in for http.client.HTTPConnection: no sockets. Set the class attributes per test."""

    status = 200
    body = b'{"on": true}'
    fail_on: str | None = None  # "request" or "getresponse"
    error: Exception = TimeoutError()
    built: ClassVar[list[tuple[str, int, float]]] = []
    sent: ClassVar[list[tuple[str, str, Any, dict[str, str]]]] = []

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.built.append((host, port, timeout))

    def request(self, method: str, path: str, data: Any, headers: dict[str, str]) -> None:
        self.sent.append((method, path, data, headers))
        if self.fail_on == "request":
            raise self.error

    def getresponse(self) -> "FakeConnection":
        if self.fail_on == "getresponse":
            raise self.error
        return self

    def read(self, amt: int) -> bytes:
        return self.body[:amt]

    def close(self) -> None:
        pass


@pytest.fixture()
def conn(monkeypatch: pytest.MonkeyPatch) -> type[FakeConnection]:
    class Fresh(FakeConnection):
        built: ClassVar[list[tuple[str, int, float]]] = []
        sent: ClassVar[list[tuple[str, str, Any, dict[str, str]]]] = []

    monkeypatch.setattr(dev.http.client, "HTTPConnection", Fresh)
    return Fresh


def get(path: str = "/x", **kw: Any) -> Any:
    return asyncio.run(dev.request("GET", "127.0.0.1", path, **kw))


def test_get_and_post_json(conn: type[FakeConnection]) -> None:
    assert get(port=8080) == {"on": True}
    assert conn.built[0] == ("127.0.0.1", 8080, dev.TIMEOUT_SECONDS)
    assert conn.sent[0] == ("GET", "/x", None, {})
    conn.body = b'{"got": {"a": 1}}'
    assert asyncio.run(dev.request("POST", "127.0.0.1", "/x", body={"a": 1})) == {"got": {"a": 1}}
    assert conn.sent[1] == ("POST", "/x", json.dumps({"a": 1}), {"Content-Type": "application/json"})


def test_errors_never_show_the_path(conn: type[FakeConnection], caplog: pytest.LogCaptureFixture) -> None:
    conn.status = 500
    with pytest.raises(dev.DeviceError) as e:
        get("/api/s3cr3t-key/lights?password=hunter2")
    assert str(e.value) == "HTTP 500"
    for secret in ("s3cr3t-key", "hunter2"):
        assert secret not in str(e.value)
        assert secret not in caplog.text


def test_not_json_and_too_large(conn: type[FakeConnection], monkeypatch: pytest.MonkeyPatch) -> None:
    conn.body = b"<html>login</html>"
    with pytest.raises(dev.DeviceError, match="not JSON"):
        get()
    monkeypatch.setattr(dev, "MAX_BYTES", 100)
    conn.body = json.dumps({"x": "y" * 500}).encode()
    with pytest.raises(dev.DeviceError, match="too large"):
        get()


@pytest.mark.parametrize("error", [TimeoutError(), ConnectionResetError()])
@pytest.mark.parametrize("stage", ["request", "getresponse"])
def test_no_answer(conn: type[FakeConnection], error: Exception, stage: str, caplog: pytest.LogCaptureFixture) -> None:
    conn.fail_on, conn.error = stage, error
    with pytest.raises(dev.DeviceError) as e:
        get("/api/s3cr3t-key/lights")
    assert str(e.value) == "no answer" and "s3cr3t-key" not in caplog.text
    assert conn.built[0][2] == dev.TIMEOUT_SECONDS


def test_timeout_uses_the_module_setting(conn: type[FakeConnection], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dev, "TIMEOUT_SECONDS", 0.2)
    get()
    assert conn.built[0][2] == 0.2
