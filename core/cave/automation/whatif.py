"""The Test Center: run the real interpreter against simulated inputs, with every effect replaced by a note."""

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from cave.automation.effects import Step, Trace
from cave.automation.engine import Engine
from cave.config.models import Automation, RunSequence, Sequence
from cave.state import State
from cave.templates import StateReader

EFFECT_STEPS = {"call", "notify", "delay", "wait_for", "script", "mqtt_publish"}
SUMMARY = "Done. 0 devices changed, 0 messages sent, 0 scripts run."


class OverlayReader:
    """Simulated states first, then the real ones."""

    def __init__(self, base: StateReader, overrides: Mapping[str, tuple[str, dict[str, Any]]], now: datetime) -> None:
        self.base, self.overrides, self.now = base, overrides, now

    def get(self, entity_id: str) -> State | None:
        if entity_id in self.overrides:
            value, attrs = self.overrides[entity_id]
            return State(entity_id, value, attrs, self.now, self.now)
        return self.base.get(entity_id)


class WhatIfEffects:
    """Does nothing. Scripts return their sample output so later steps still have something to use."""

    def __init__(self, reader: OverlayReader, script_samples: Mapping[str, dict[str, Any]]) -> None:
        self.reader, self.samples = reader, script_samples
        self.assumed: set[str] = set()

    async def call(self, entity_id: str, command: str, args: dict[str, Any]) -> None:
        pass

    async def notify(self, targets: list[str], title: str | None, message: str, source: str) -> None:
        pass

    async def mqtt_publish(self, topic: str, payload: str, retain: bool) -> None:
        pass

    async def run_script(self, ref: str, target: str | None, args: dict[str, Any], source: str) -> dict[str, Any]:
        return dict(self.samples.get(ref, {}))

    async def sleep(self, seconds: float) -> None:
        pass

    async def wait_for_state(self, entity_id: str, to: str, timeout: float) -> bool:
        if entity_id in self.reader.overrides:
            return self.reader.overrides[entity_id][0] == to
        self.assumed.add(entity_id)
        return True


def _overrides(states: Mapping[str, str | dict[str, Any]]) -> dict[str, tuple[str, dict[str, Any]]]:
    out: dict[str, tuple[str, dict[str, Any]]] = {}
    for entity_id, v in states.items():
        if isinstance(v, dict):
            out[entity_id] = (str(v.get("state", "unknown")), dict(v.get("attributes", {})))
        else:
            out[entity_id] = (str(v), {})
    return out


def _relabel(trace: Trace, assumed: set[str]) -> None:
    for step in trace.steps:
        if step.type not in EFFECT_STEPS or step.result not in ("ok", "stopped"):
            continue
        note = {"script": " (not run; using sample output)", "delay": " (skipped)"}.get(step.type, "")
        if step.type == "wait_for" and step.data.get("entity") in assumed:
            note = " (assumed: no simulated value given)"
        step.result, step.detail = "what_if", f"What if: {step.detail}{note}"


async def what_if(
    doc: Automation | Sequence,
    *,
    trigger: dict[str, Any] | None,
    states: Mapping[str, str | dict[str, Any]],
    variables: dict[str, Any],
    start_at: str | None,
    script_samples: Mapping[str, dict[str, Any]],
    reader: StateReader,
    sequences: Callable[[str], Sequence | None],
    now: datetime,
) -> Trace:
    overlay = OverlayReader(reader, _overrides(states), now)
    effects = WhatIfEffects(overlay, script_samples)
    if isinstance(doc, Sequence):  # run it the way an automation would call it, so fields get their types

        def lookup(ident: str) -> Sequence | None:
            return doc if ident == doc.id else sequences(ident)

        engine = Engine(overlay, effects, lookup, lambda: now)
        call = RunSequence.model_validate({"type": "sequence", "ref": f"sequence.{doc.id}", "with": variables})
        trace = await engine.run([call], {}, start_at=start_at, source="test")
    else:
        engine = Engine(overlay, effects, sequences, lambda: now)
        scope = {"trigger": trigger or {}, **variables}
        if start_at is None:
            ok, steps = await engine.check(doc.conditions, scope)
            if not ok:
                return Trace(steps=steps, outcome="conditions_not_met", variables=scope)
        trace = await engine.run(doc.actions, scope, start_at=start_at, source="test")
    _relabel(trace, effects.assumed)
    trace.steps.append(Step("summary", "summary", SUMMARY, now))
    return trace
