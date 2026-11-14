"""A stand-in for `cave.integrations.http.request`: canned replies, no sockets."""

from typing import Any

from cave.integrations.http import DeviceError


class FakeHttp:
    def __init__(self, routes: dict[tuple[str, str], Any]) -> None:
        self.routes = routes
        self.offline = False
        self.calls: list[tuple[str, str, str, Any]] = []

    async def __call__(self, method: str, host: str, path: str, *, port: int = 80, body: Any = None) -> Any:
        self.calls.append((method, host, path, body))
        if self.offline:
            raise DeviceError("no answer")
        if (method, path) not in self.routes:
            raise DeviceError("HTTP 404")
        reply = self.routes[(method, path)]
        return reply(body) if callable(reply) else reply
