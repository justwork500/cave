"""A small JSON-over-HTTP client for LAN devices.

Errors carry only a short reason: never the path, query or body, because those can hold a key or password.
"""

import asyncio
import http.client
import json
from collections.abc import Awaitable, Callable
from typing import Any

TIMEOUT_SECONDS = 5.0
MAX_BYTES = 1_000_000
NOT_RESPONDING = "This device isn't responding."

Fetch = Callable[..., Awaitable[Any]]


class DeviceError(Exception):
    """The device didn't answer usefully. The message never contains the path, query or body."""


def _request(method: str, host: str, path: str, port: int, body: Any) -> Any:
    conn = http.client.HTTPConnection(host, port, timeout=TIMEOUT_SECONDS)
    try:
        data = None if body is None else json.dumps(body)
        headers = {} if body is None else {"Content-Type": "application/json"}
        try:
            conn.request(method, path, data, headers)
            resp = conn.getresponse()
            raw = resp.read(MAX_BYTES + 1)
        except (OSError, http.client.HTTPException):
            raise DeviceError("no answer") from None
        if resp.status >= 400:
            raise DeviceError(f"HTTP {resp.status}")
        if len(raw) > MAX_BYTES:
            raise DeviceError("too large")
        try:
            return json.loads(raw)
        except ValueError:
            raise DeviceError("not JSON") from None
    finally:
        conn.close()


async def request(method: str, host: str, path: str, *, port: int = 80, body: Any = None) -> Any:
    return await asyncio.to_thread(_request, method, host, path, port, body)
