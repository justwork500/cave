"""The broker connection: connect, subscribe, feed the bridge, reconnect with backoff."""

import asyncio
import logging
from typing import Literal

import aiomqtt

from cave.db import Database
from cave.integrations.mqtt.bridge import MqttBridge
from cave.integrations.mqtt.config import MqttConfig
from cave.state import StateMachine

log = logging.getLogger(__name__)

Status = Literal["disabled", "connecting", "connected", "failed"]
AUTH_FAILURES = {4, 5, 134, 135}  # MQTT 3.1.1 and 5 codes for bad credentials / not authorised


def backoff(attempt: int) -> float:
    return float(min(60, 2**attempt))


def _payload(raw: object) -> bytes:
    if isinstance(raw, bytes | bytearray):
        return bytes(raw)
    if raw is None:
        return b""
    return str(raw).encode()


def _code(error: aiomqtt.MqttError) -> int | None:
    rc = getattr(error, "rc", None)
    value = getattr(rc, "value", rc)
    return value if isinstance(value, int) else None


class MqttService:
    def __init__(self, cfg: MqttConfig, db: Database, states: StateMachine, password: str | None) -> None:
        self.cfg = cfg
        self.password = password
        self.status: Status = "connecting"
        self.last_error: str | None = None
        self._client: aiomqtt.Client | None = None
        self.bridge = MqttBridge(db, states, self._publish, cfg.discovery_prefix)
        for entity in cfg.entities:
            self.bridge.add_manual(entity)

    async def _publish(self, topic: str, payload: str, retain: bool) -> None:
        if self._client is None or self.status != "connected":
            raise ValueError("The MQTT broker isn't connected right now.")
        await self._client.publish(topic, payload, retain=retain)

    async def run(self) -> None:
        b = self.cfg.broker
        attempt = 0
        while True:
            try:
                async with aiomqtt.Client(
                    b.host, b.port, username=b.username, password=self.password,
                    tls_params=aiomqtt.TLSParameters() if b.tls else None,
                ) as client:
                    self._client = client
                    self.status, self.last_error, attempt = "connected", None, 0
                    log.info("MQTT connected to %s:%s", b.host, b.port)
                    for topic in sorted(self.bridge.subscriptions()):
                        await client.subscribe(topic)
                    async for message in client.messages:
                        for topic in sorted(await self.bridge.handle(str(message.topic), _payload(message.payload))):
                            await client.subscribe(topic)
            except aiomqtt.MqttError as e:
                self._client = None
                failed = _code(e) in AUTH_FAILURES
                self.status = "failed" if failed else "connecting"
                self.last_error = str(e)
                delay = 60.0 if failed else backoff(attempt)
                attempt += 1
                log.warning("MQTT %s (%s); retrying in %.0f s", self.status, e, delay)
                await asyncio.sleep(delay)
