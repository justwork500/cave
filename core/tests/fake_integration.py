"""A recording integration for API tests: no network, a settable answer per host."""

import asyncio

from cave.integrations.base import Device, Found, Pairing


class FakeIntegration:
    title = "Fake"
    pairing_hint = "Press the fake button."

    def __init__(self, domain: str = "fake", pairing: Pairing = "key") -> None:
        self.domain = domain
        self.pairing: Pairing = pairing
        self.answers: dict[str, Found] = {}
        self.calls: list[tuple[str, str]] = []
        self.pair_error: Exception | None = None
        self.attach_fails: set[str] = set()
        self.probe_delay = 0.0
        self.probe_error: Exception | None = None
        self.pair_delay = 0.0
        self.detach_fails = False
        self.secrets: list[str | None] = []

    async def probe(self, host: str) -> Found | None:
        self.calls.append(("probe", host))
        await asyncio.sleep(self.probe_delay)
        if self.probe_error is not None:
            raise self.probe_error
        return self.answers.get(host)

    async def pair(self, host: str, secret: str | None) -> tuple[Found, dict[str, str]]:
        self.calls.append(("pair", host))
        self.secrets.append(secret)
        await asyncio.sleep(self.pair_delay)
        if self.pair_error is not None:
            raise self.pair_error
        return self.answers[host], {"key": secret or ""}

    def attach(self, device: Device) -> None:
        self.calls.append(("attach", f"{device.device_id}@{device.host}"))
        if device.device_id in self.attach_fails:
            raise RuntimeError("boom")

    def detach(self, device_id: str) -> None:
        self.calls.append(("detach", device_id))
        if self.detach_fails:
            raise KeyError(device_id)

    async def run(self) -> None:
        await asyncio.Event().wait()
