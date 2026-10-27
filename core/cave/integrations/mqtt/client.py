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
        try:
            await self._client.publish(topic, payload, retain=retain)
        except aiomqtt.MqttError as e:
            raise ValueError("The MQTT broker didn't take the message. Try again.") from e

    async def _subscribe(self, client: aiomqtt.Client, topics: set[str]) -> None:
        if topics:
            await client.subscribe([(t, 0) for t in sorted(topics)])

    def _fail(self, status: Status, error: Exception, attempt: int) -> float:
        self._client = None
        self.status, self.last_error = status, str(error)
        delay = 60.0 if status == "failed" else backoff(attempt)
        log.warning("MQTT %s (%s); retrying in %.0f s", status, error, delay)
        return delay

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
                    await self._subscribe(client, self.bridge.subscriptions())
                    async for message in client.messages:
                        try:
                            new = await self.bridge.handle(str(message.topic), _payload(message.payload))
                            await self._subscribe(client, new)
                        except aiomqtt.MqttError:
                            raise
                        except Exception:
                            # one bad message must never stop the house's MQTT
                            log.exception("MQTT message on %s could not be handled", message.topic)
                delay = self._fail("connecting", aiomqtt.MqttError("the broker closed the connection"), attempt)
            except aiomqtt.MqttError as e:
                delay = self._fail("failed" if _code(e) in AUTH_FAILURES else "connecting", e, attempt)
            except Exception as e:  # anything unexpected: report it and keep retrying
                log.exception("MQTT connection loop error")
                delay = self._fail("failed", e, attempt)
            attempt += 1
            await asyncio.sleep(delay)
