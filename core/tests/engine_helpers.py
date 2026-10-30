import asyncio
from datetime import datetime
from typing import Any

from cave.config.models import Automation, AutomationFile, Sequence, SequenceFile
from cave.config.yamlfile import load_text, validate
from cave.state import State

NOON = datetime(2026, 1, 7, 12, 0)  # a Wednesday


class DictReader:
    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.values = dict(values or {})

    def get(self, entity_id: str) -> State | None:
        if entity_id not in self.values:
            return None
        return State(entity_id, self.values[entity_id], {}, NOON, NOON)


class FakeEffects:
    def __init__(self, reader: DictReader | None = None, wait_result: bool = True,
                 script_result: dict[str, Any] | None = None) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self.reader = reader
        self.wait_result = wait_result
        self.script_result = script_result or {"status": "ok"}

    async def call(self, entity_id: str, command: str, args: dict[str, Any]) -> None:
        self.calls.append(("call", entity_id, command, args))
        if self.reader is not None and command in ("turn_on", "turn_off"):
            self.reader.values[entity_id] = command[5:]

    async def notify(self, targets: list[str], title: str | None, message: str, source: str) -> None:
        self.calls.append(("notify", tuple(targets), title, message))

    async def mqtt_publish(self, topic: str, payload: str, retain: bool) -> None:
        self.calls.append(("mqtt", topic, payload, retain))

    async def run_script(self, ref: str, target: str | None, args: dict[str, Any], source: str) -> dict[str, Any]:
        self.calls.append(("script", ref, target, args, source))
        return self.script_result

    async def sleep(self, seconds: float) -> None:
        self.calls.append(("sleep", seconds))

    async def wait_for_state(self, entity_id: str, to: str, timeout: float) -> bool:
        self.calls.append(("wait", entity_id, to, timeout))
        return self.wait_result


def automation(body: str, extra: str = "") -> Automation:
    text = f"automation:\n  id: a\n  name: A\n  triggers:\n    - type: startup\n{extra}  actions:\n{body}"
    return validate(AutomationFile, load_text(text, "a.yaml"), "a.yaml").automation


def sequence(text: str) -> Sequence:
    return validate(SequenceFile, load_text(text, "s.yaml"), "s.yaml").sequence


def run(coro: Any) -> Any:
    return asyncio.run(coro)
