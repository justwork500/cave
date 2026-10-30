"""The automation interpreter: conditions and actions, one Step per action in the trace."""

import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import Any

from cave.automation.effects import Effects, Step, StepResult, Trace
from cave.config.models import (
    Action,
    AndCondition,
    Call,
    Choose,
    Condition,
    Delay,
    MqttPublish,
    NotCondition,
    Notify,
    NumericStateCondition,
    OrCondition,
    Repeat,
    RunSequence,
    Script,
    Sequence,
    SetVariable,
    StateCondition,
    Stop,
    TemplateCondition,
    TimeCondition,
    WaitFor,
)
from cave.templates import StateReader, TemplateError, render

MAX_REPEAT = 1000
MAX_STEPS = 10_000  # per run, across every repeat, branch and routine
YIELD_EVERY = 100
MAX_DEPTH = 8
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
TRUTHY = {"true", "yes", "on", "1"}
_CAST: dict[str, Callable[[Any], Any]] = {
    "int": int, "float": float, "str": str, "bool": lambda v: str(v).strip().lower() in TRUTHY,
}


class _Stopped(Exception):
    pass


class StepFailed(Exception):
    pass


class Engine:
    def __init__(
        self,
        reader: StateReader,
        effects: Effects,
        sequences: Callable[[str], Sequence | None],
        now: Callable[[], datetime],
    ) -> None:
        self.reader = reader
        self.effects = effects
        self.sequences = sequences
        self.now = now

    # ---- templates ----

    def _render(self, value: Any, variables: dict[str, Any]) -> Any:
        if isinstance(value, str):
            return render(value, variables, self.reader, self.now()) if "{" in value else value
        if isinstance(value, dict):
            return {k: self._render(v, variables) for k, v in value.items()}
        if isinstance(value, list):
            return [self._render(v, variables) for v in value]
        return value

    # ---- conditions ----

    async def check(self, conditions: list[Condition], variables: dict[str, Any]) -> tuple[bool, list[Step]]:
        steps: list[Step] = []
        # a list, not a generator: every condition is evaluated and recorded, even after one fails
        ok = all([self._cond(c, variables, steps, f"conditions[{i}]") for i, c in enumerate(conditions)])  # noqa: C419
        return ok, steps

    def _cond(self, c: Condition, variables: dict[str, Any], steps: list[Step], path: str) -> bool:
        result = self._eval(c, variables, steps, path)
        steps.append(Step(path, c.type, f"{c.type}: {'passed' if result else 'not met'}", self.now(),
                          "ok" if result else "stopped"))
        return result

    def _eval(self, c: Condition, variables: dict[str, Any], steps: list[Step], path: str) -> bool:
        if isinstance(c, StateCondition):
            s = self.reader.get(c.entity)
            wanted = [c.state] if isinstance(c.state, str) else c.state
            return s is not None and s.value in wanted
        if isinstance(c, NumericStateCondition):
            s = self.reader.get(c.entity)
            try:
                v = float(s.value) if s else None
            except ValueError:
                v = None
            return v is not None and (c.above is None or v > c.above) and (c.below is None or v < c.below)
        if isinstance(c, TimeCondition):
            n = self.now()
            if c.weekdays is not None and WEEKDAYS[n.weekday()] not in c.weekdays:
                return False
            t = n.time().replace(tzinfo=None)
            if c.after and c.before and c.after > c.before:  # a window across midnight
                return t >= c.after or t < c.before
            return (c.after is None or t >= c.after) and (c.before is None or t < c.before)
        if isinstance(c, TemplateCondition):
            try:
                return str(self._render(c.value, variables)).strip().lower() in TRUTHY
            except TemplateError:
                return False
        subs = [self._cond(x, variables, steps, f"{path}.conditions[{i}]") for i, x in enumerate(c.conditions)]
        if isinstance(c, AndCondition):
            return all(subs)
        if isinstance(c, OrCondition):
            return any(subs)
        assert isinstance(c, NotCondition)
        return not any(subs)

    # ---- actions ----

    async def run(
        self, actions: list[Action], variables: dict[str, Any], *, start_at: str | None = None, source: str
    ) -> Trace:
        trace = Trace(variables=variables)
        self._steps = 0
        self._source = source
        self._start_at = start_at
        try:
            await self._run(actions, "actions", variables, trace, 0)
            if self._start_at is not None:
                raise StepFailed(f"There's no step at {start_at}.")
        except _Stopped:
            trace.outcome = "stopped"
        except StepFailed as e:
            trace.outcome, trace.error = "failed", str(e)
        return trace

    def _skipping(self, path: str) -> tuple[bool, bool]:
        """(skip this step, descend into it to reach the start point)."""
        if self._start_at is None:
            return False, False
        if self._start_at == path:
            self._start_at = None
            return False, False
        return True, self._start_at.startswith(path + ".")

    async def _run(self, actions: list[Action], base: str, variables: dict[str, Any], trace: Trace,
                   depth: int) -> None:
        for i, action in enumerate(actions):
            path = f"{base}[{i}]"
            skip, descend = self._skipping(path)
            if skip and not descend:
                trace.steps.append(Step(path, action.type, "skipped (before the start point)", self.now(), "skipped"))
                continue
            self._steps += 1
            if self._steps > MAX_STEPS:
                raise StepFailed(f"A run can take at most {MAX_STEPS} steps.")
            if self._steps % YIELD_EVERY == 0:
                await asyncio.sleep(0)  # long runs that never wait must not freeze the server
            step = Step(path, action.type, action.type, self.now())
            trace.steps.append(step)
            try:
                await self._do(action, path, variables, trace, depth, step, descend)
            except (_Stopped, StepFailed):
                raise
            except Exception as e:  # any failure inside a step ends the run as failed
                step.result, step.detail = "failed", f"{action.type} failed: {e}"
                raise StepFailed(step.detail) from e

    def _mark(self, step: Step, detail: str, result: StepResult = "ok", **data: Any) -> None:
        if step.result != "what_if":
            step.result = result
        step.detail = detail
        step.data.update(data)

    async def _do(self, a: Action, path: str, variables: dict[str, Any], trace: Trace, depth: int, step: Step,
                  descend: bool) -> None:
        if isinstance(a, Call):
            args = self._render(a.args, variables)
            await self.effects.call(a.target, a.command, args)
            self._mark(step, f"{a.command} {a.target}", entity=a.target, command=a.command, args=args)
        elif isinstance(a, Notify):
            title = self._render(a.title, variables)
            message = self._render(a.message, variables)
            await self.effects.notify(a.targets, title, message, self._source)
            self._mark(step, f"notify: {message}", title=title, message=message)
        elif isinstance(a, Delay):
            await self.effects.sleep(a.duration.total_seconds())
            self._mark(step, f"wait {a.duration}")
        elif isinstance(a, WaitFor):
            ok = await self.effects.wait_for_state(a.entity, a.to, a.timeout.total_seconds())
            if not ok and a.on_timeout == "stop":
                self._mark(step, f"{a.entity} didn't become {a.to} within {a.timeout}; stopping", "stopped")
                raise _Stopped
            self._mark(step, f"{a.entity} is {a.to}" if ok else f"timed out after {a.timeout}; continuing")
        elif isinstance(a, Choose):
            await self._choose(a, path, variables, trace, depth, step, descend)
        elif isinstance(a, Repeat):
            await self._repeat(a, path, variables, trace, depth, step)
        elif isinstance(a, RunSequence):
            await self._sequence(a, path, variables, trace, depth, step)
        elif isinstance(a, Script):
            args = self._render(a.args, variables)
            result = await self.effects.run_script(a.ref, a.target, args, self._source)
            if a.result_var:
                variables[a.result_var] = result
            self._mark(step, f"script {a.ref}", ref=a.ref, args=args, output=result)
        elif isinstance(a, SetVariable):
            variables[a.name] = self._render(a.value, variables)
            self._mark(step, f"{a.name} = {variables[a.name]!r}")
        elif isinstance(a, Stop):
            self._mark(step, f"stop{': ' + a.reason if a.reason else ''}", "stopped")
            raise _Stopped
        elif isinstance(a, MqttPublish):
            payload = self._render(a.payload, variables)
            await self.effects.mqtt_publish(a.topic, payload, a.retain)
            self._mark(step, f"publish to {a.topic}", topic=a.topic, payload=payload)

    async def _choose(self, a: Choose, path: str, variables: dict[str, Any], trace: Trace, depth: int, step: Step,
                      descend: bool) -> None:
        if descend:  # the start point is inside one branch: enter it without checking conditions
            assert self._start_at is not None
            rest = self._start_at[len(path) + 1:]
            if rest.startswith("default"):
                self._mark(step, "starting inside the default branch")
                await self._run(a.default, f"{path}.default", variables, trace, depth)
                return
            j = int(rest.split("[", 1)[1].split("]", 1)[0])
            self._mark(step, f"starting inside option {j + 1}")
            await self._run(a.options[j].actions, f"{path}.options[{j}].actions", variables, trace, depth)
            return
        for j, opt in enumerate(a.options):
            ok, _ = await self.check(opt.conditions, variables)
            if ok:
                self._mark(step, f"option {j + 1} chosen")
                await self._run(opt.actions, f"{path}.options[{j}].actions", variables, trace, depth)
                return
        self._mark(step, "no option matched; default" if a.default else "no option matched")
        await self._run(a.default, f"{path}.default", variables, trace, depth)

    async def _repeat(self, a: Repeat, path: str, variables: dict[str, Any], trace: Trace, depth: int,
                      step: Step) -> None:
        n = 0
        while n < MAX_REPEAT:
            if a.count is not None and n >= a.count:
                break
            if a.while_ is not None and not (await self.check(a.while_, variables))[0]:
                break
            variables["repeat"] = {"index": n + 1}
            await self._run(a.actions, f"{path}.actions", variables, trace, depth)
            n += 1
            if a.until is not None and (await self.check(a.until, variables))[0]:
                break
        self._mark(step, f"repeated {n} time{'s' if n != 1 else ''}", iterations=n)

    async def _sequence(self, a: RunSequence, path: str, variables: dict[str, Any], trace: Trace, depth: int,
                        step: Step) -> None:
        ident = a.ref.split(".", 1)[1]
        if depth + 1 > MAX_DEPTH:
            raise StepFailed(f"Routines can call routines only {MAX_DEPTH} deep (is {ident!r} calling itself?).")
        seq = self.sequences(ident)
        if seq is None:
            raise StepFailed(f"There's no routine called {ident!r}.")
        given = self._render(a.with_, variables)
        child: dict[str, Any] = {}
        for name, f in seq.fields.items():
            value = given.get(name, f.default)
            try:
                child[name] = None if value is None else _CAST[f.type](value)
            except (TypeError, ValueError) as e:
                raise StepFailed(f"{ident}: {name} must be a {f.type}, not {value!r}.") from e
        self._mark(step, f"run routine {ident}", ref=ident, fields=child)
        await self._run(list(seq.actions), f"{path}[{ident}].actions", child, trace, depth + 1)
