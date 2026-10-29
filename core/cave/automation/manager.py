"""Runs automations: arms their triggers, applies run modes, and keeps their traces."""

import asyncio
import contextlib
import dataclasses
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from cave.access.items import get_item
from cave.automation.effects import Effects, Trace
from cave.automation.engine import Engine
from cave.config.models import (
    Automation,
    NumericStateTrigger,
    StartupTrigger,
    StateTrigger,
    TimePatternTrigger,
    TimeTrigger,
)
from cave.config.store import ConfigStore
from cave.db import Database
from cave.state import Event, EventBus, StateMachine

log = logging.getLogger(__name__)
KEEP_TRACES = 20
Sleep = Callable[[float], Awaitable[None]]


def _local_now() -> datetime:
    return datetime.now().astimezone()


def _in_range(t: NumericStateTrigger, value: str | None) -> bool:
    try:
        v = float(value) if value is not None else None
    except ValueError:
        return False
    return v is not None and (t.above is None or v > t.above) and (t.below is None or v < t.below)


def _pattern(spec: int | str, value: int) -> bool:
    if spec == "*":
        return True
    if isinstance(spec, str):
        return value % int(spec[1:]) == 0
    return spec == value


class AutomationManager:
    def __init__(
        self,
        store: ConfigStore,
        db: Database,
        states: StateMachine,
        bus: EventBus,
        effects: Effects,
        now: Callable[[], datetime] = _local_now,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self.store, self.db, self.states, self.bus, self.effects = store, db, states, bus, effects
        self.now, self.sleep = now, sleep
        self._armed: dict[str, Automation] = {}
        self._timers: dict[tuple[str, int], asyncio.Task[None]] = {}
        self._running: dict[str, list[asyncio.Task[None]]] = {}
        self._queued: dict[str, list[tuple[int, dict[str, Any], bool]]] = {}
        self._tasks: list[asyncio.Task[None]] = []
        self._last_tick: tuple[int, int, int, int, int] | None = None

    # ---- lifecycle ----

    async def start(self) -> None:
        self.rearm()
        queue = self.bus.subscribe()
        self._tasks = [asyncio.create_task(self._consume(queue)), asyncio.create_task(self._ticker())]
        self._queue = queue
        for aid, a in list(self._armed.items()):
            if any(isinstance(t, StartupTrigger) for t in a.triggers):
                self.fire(aid, {"type": "startup"})

    async def stop(self) -> None:
        self.bus.unsubscribe(self._queue)
        everything = [*self._tasks, *self._timers.values(), *(t for ts in self._running.values() for t in ts)]
        for t in everything:
            t.cancel()
        for t in everything:
            with contextlib.suppress(asyncio.CancelledError):
                await t
        self._timers.clear()

    def rearm(self) -> None:
        """Rebuild which automations listen for what. Called after every load or save."""
        for t in self._timers.values():
            t.cancel()
        self._timers.clear()
        self._armed = {}
        for ident, loaded in self.store.list("automation"):
            a = loaded.doc
            item = get_item(self.db, f"automation:{ident}")
            if isinstance(a, Automation) and a.enabled and item is not None and item.status == "enabled":
                self._armed[ident] = a

    # ---- triggers ----

    async def _consume(self, queue: "asyncio.Queue[Event]") -> None:
        while True:
            event = await queue.get()
            if event.get("type") == "state_changed":
                try:
                    self._on_state(event)
                except Exception:
                    log.exception("automation trigger handling failed")

    def _on_state(self, event: Event) -> None:
        entity, old, new = event["entity_id"], event["old"], event["new"]
        if old == new:
            return  # attributes only
        for aid, a in list(self._armed.items()):
            for i, t in enumerate(a.triggers):
                if not isinstance(t, StateTrigger | NumericStateTrigger) or t.entity != entity:
                    continue
                if isinstance(t, StateTrigger):
                    matches = (t.from_ is None or t.from_ == old) and (t.to is None or t.to == new)
                    still = (lambda t=t, new=new: self._current(t.entity) == new)
                else:
                    matches = _in_range(t, new) and not _in_range(t, old)
                    still = (lambda t=t: _in_range(t, self._current(t.entity)))
                key = (aid, i)
                if key in self._timers and not still():
                    self._timers.pop(key).cancel()
                if not matches:
                    continue
                data = {"type": t.type, "entity": entity, "from": old, "to": new}
                if t.for_ is None:
                    self.fire(aid, data)
                else:
                    if key in self._timers:
                        self._timers.pop(key).cancel()
                    self._timers[key] = asyncio.create_task(self._after(key, t.for_.total_seconds(), still, data))

    def _current(self, entity_id: str) -> str | None:
        s = self.states.get(entity_id)
        return s.value if s else None

    async def _after(self, key: tuple[str, int], seconds: float, still: Callable[[], bool], data: dict[str, Any]
                     ) -> None:
        await self.sleep(seconds)
        self._timers.pop(key, None)
        if still():
            self.fire(key[0], data)

    async def _ticker(self) -> None:
        while True:
            n = self.now()
            await self.sleep(60 - n.second - n.microsecond / 1e6)
            await self.tick()

    async def tick(self) -> None:
        n = self.now()
        stamp = (n.year, n.month, n.day, n.hour, n.minute)
        if stamp == self._last_tick:
            return
        self._last_tick = stamp
        for aid, a in list(self._armed.items()):
            for t in a.triggers:
                if (isinstance(t, TimeTrigger) and (t.at.hour, t.at.minute) == (n.hour, n.minute)) or (
                    isinstance(t, TimePatternTrigger) and _pattern(t.minutes, n.minute) and _pattern(t.hours, n.hour)
                ):
                    self.fire(aid, {"type": t.type, "at": n.isoformat()})

    # ---- runs ----

    def fire(self, aid: str, trigger: dict[str, Any], check_conditions: bool = True) -> int | None:
        """Start (or queue, or drop) a run as the run mode says. Returns its trace id, or None if dropped."""
        a = self._armed.get(aid) or self._loaded(aid)
        if a is None:
            return None
        running = [t for t in self._running.get(aid, []) if not t.done()]
        self._running[aid] = running
        if running and a.mode == "single":
            log.info("automation %s is already running; trigger dropped", aid)
            return None
        if a.mode == "parallel" and len(running) >= a.max:
            return None
        if running and a.mode == "queued":
            waiting = self._queued.setdefault(aid, [])
            if len(waiting) >= a.max:
                return None
            trace_id = self.new_trace(f"automation:{aid}")
            waiting.append((trace_id, trigger, check_conditions))
            return trace_id
        if a.mode == "restart":
            for t in running:
                t.cancel()
        trace_id = self.new_trace(f"automation:{aid}")
        self._start(aid, a, trace_id, trigger, check_conditions)
        return trace_id

    def _loaded(self, aid: str) -> Automation | None:
        loaded = self.store.get("automation", aid)
        return loaded.doc if loaded and isinstance(loaded.doc, Automation) else None

    def _start(self, aid: str, a: Automation, trace_id: int, trigger: dict[str, Any], check: bool) -> None:
        task = asyncio.create_task(self._run(aid, a, trace_id, trigger, check))
        self._running.setdefault(aid, []).append(task)

    async def _run(self, aid: str, a: Automation, trace_id: int, trigger: dict[str, Any], check: bool) -> None:
        engine = Engine(self.states, self.effects, self.store.sequence, self.now)
        variables: dict[str, Any] = {"trigger": trigger}
        trace = Trace(variables=variables)
        try:
            if check:
                ok, steps = await engine.check(a.conditions, variables)
                if not ok:
                    trace.steps, trace.outcome = steps, "conditions_not_met"
                    return
            trace = await engine.run(a.actions, variables, source=f"automation:{aid}")
        except asyncio.CancelledError:
            trace.outcome = "cancelled"
            raise
        except Exception as e:  # never let one automation take the manager down
            log.exception("automation %s failed", aid)
            trace.outcome, trace.error = "failed", str(e)
        finally:
            self.finish_trace(f"automation:{aid}", trace_id, trace)
            waiting = self._queued.get(aid)
            if waiting and trace.outcome != "cancelled":
                next_id, next_trigger, next_check = waiting.pop(0)
                self._start(aid, a, next_id, next_trigger, next_check)

    # ---- traces ----

    def new_trace(self, item_id: str, test: bool = False) -> int:
        cur = self.db.execute(
            "INSERT INTO automation_traces (item_id, test, started_at) VALUES (?, ?, ?)",
            (item_id, int(test), datetime.now(UTC).isoformat()),
        )
        assert cur.lastrowid is not None
        return cur.lastrowid

    def finish_trace(self, item_id: str, trace_id: int, trace: Trace) -> None:
        body = json.dumps(dataclasses.asdict(trace), default=str)
        self.db.execute(
            "UPDATE automation_traces SET finished_at=?, outcome=?, trace=? WHERE id=?",
            (datetime.now(UTC).isoformat(), trace.outcome, body, trace_id),
        )
        self.db.execute(
            "DELETE FROM automation_traces WHERE item_id=? AND test=(SELECT test FROM automation_traces WHERE id=?) "
            "AND id NOT IN (SELECT id FROM automation_traces WHERE item_id=? AND test="
            "(SELECT test FROM automation_traces WHERE id=?) ORDER BY id DESC LIMIT ?)",
            (item_id, trace_id, item_id, trace_id, KEEP_TRACES),
        )

    def traces(self, item_id: str, test: bool = False, limit: int = KEEP_TRACES) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT id, started_at, finished_at, outcome, trace FROM automation_traces "
            "WHERE item_id=? AND test=? AND finished_at IS NOT NULL ORDER BY id DESC LIMIT ?",
            (item_id, int(test), limit),
        ).fetchall()
        return [dict(r) | {"trace": json.loads(r["trace"])} for r in rows]
