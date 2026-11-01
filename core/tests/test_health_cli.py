import io
import json
import urllib.error

import pytest

from cave import __main__ as cli


class Reply(io.BytesIO):
    def __init__(self, status: int, body: object) -> None:
        super().__init__(json.dumps(body).encode())
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def run_health(monkeypatch, result):
    seen = {}

    def fake(url, timeout, context):
        seen["url"], seen["timeout"] = url, timeout
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake)
    with pytest.raises(SystemExit) as e:
        cli.main(["health"])
    return e.value.code, seen


def test_health_ok(monkeypatch):
    code, seen = run_health(monkeypatch, Reply(200, {"status": "ok"}))
    assert code == 0
    assert seen["url"] == "https://127.0.0.1:8443/api/v1/health" and seen["timeout"] <= 5


@pytest.mark.parametrize("result", [
    Reply(503, {"status": "ok"}),
    Reply(200, {"status": "starting"}),
    urllib.error.URLError("refused"),
    TimeoutError(),
])
def test_health_fails(monkeypatch, result):
    assert run_health(monkeypatch, result)[0] == 1
