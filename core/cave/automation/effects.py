"""What the engine does to the world goes through Effects; what it reads goes through a StateReader.

A real run and a Test Center run share the interpreter and differ only in these two objects.
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol

from cave import notifications
from cave.db import Database
from cave.integrations.mqtt.bridge import MqttBridge
from cave.scripts.service import ScriptService
from cave.state import EventBus, StateMachine

StepResult = Literal["ok", "skipped", "failed", "stopped", "what_if"]
Outcome = Literal["finished", "stopped", "failed", "cancelled", "conditions_not_met"]


class Effects(Protocol):
    async def call(self, entity_id: str, command: str, args: dict[str, Any]) -> None: ...
    async def notify(self, targets: list[str], title: str | None, message: str, source: str) -> None: ...
    async def mqtt_publish(self, topic: str, payload: str, retain: bool) -> None: ...
    async def run_script(
        self, ref: str, target: str | None, args: dict[str, Any], source: str
    ) -> dict[str, Any]: ...
    async def sleep(self, seconds: float) -> None: ...
    async def wait_for_state(self, entity_id: str, to: str, timeout: float) -> bool: ...


@dataclass
class Step:
    path: str
    type: str
    detail: str
    started_at: datetime
    result: StepResult = "ok"
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class Trace:
    steps: list[Step] = field(default_factory=list)
    outcome: Outcome = "finished"
    variables: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class LiveEffects:
    """The real world. Automations act as the system; the save guard already checked their author."""

    def __init__(
        self,
        states: StateMachine,
        db: Database,
        bus: EventBus,
        mqtt: Callable[[], MqttBridge | None],
        scripts: ScriptService | None = None,
    ) -> None:
        self.states, self.db, self.bus, self.mqtt, self.scripts = states, db, bus, mqtt, scripts

    async def call(self, entity_id: str, command: str, args: dict[str, Any]) -> None:
        await self.states.command(entity_id, command, args)

    async def notify(self, targets: list[str], title: str | None, message: str, source: str) -> None:
        notifications.create(self.db, self.bus, notifications.recipients(self.db, targets, source), title, message,
                             source)

    async def mqtt_publish(self, topic: str, payload: str, retain: bool) -> None:
        bridge = self.mqtt()
        if bridge is None:
            raise ValueError("MQTT isn't set up.")
        await bridge.publish(topic, payload, retain)

    async def run_script(self, ref: str, target: str | None, args: dict[str, Any], source: str) -> dict[str, Any]:
        if not ref.startswith("scripts/"):
            raise ValueError("Scripts are referenced as scripts/<file>.")
        if target not in (None, "sandbox"):
            raise ValueError("Only the sandbox target is available in this version.")
        if self.scripts is None:
            raise ValueError("The script runner isn't set up.")
        return await self.scripts.run(ref.removeprefix("scripts/"), args, source)

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)

    async def wait_for_state(self, entity_id: str, to: str, timeout: float) -> bool:
        queue = self.bus.subscribe()
        try:
            current = self.states.get(entity_id)
            if current is not None and current.value == to:
                return True
            async with asyncio.timeout(timeout):
                while True:
                    event = await queue.get()
                    if event.get("type") == "state_changed" and event["entity_id"] == entity_id and event["new"] == to:
                        return True
        except TimeoutError:
            return False
        finally:
            self.bus.unsubscribe(queue)
