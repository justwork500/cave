"""What the engine does to the world goes through Effects; what it reads goes through a StateReader.

A real run and a Test Center run share the interpreter and differ only in these two objects.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol

StepResult = Literal["ok", "skipped", "failed", "stopped", "what_if"]
Outcome = Literal["finished", "stopped", "failed", "cancelled", "conditions_not_met"]


class Effects(Protocol):
    async def call(self, entity_id: str, command: str, args: dict[str, Any]) -> None: ...
    async def notify(self, targets: list[str], title: str | None, message: str, source: str) -> None: ...
    async def mqtt_publish(self, topic: str, payload: str, retain: bool) -> None: ...
    async def run_script(self, ref: str, target: str | None, args: dict[str, Any]) -> dict[str, Any]: ...
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
