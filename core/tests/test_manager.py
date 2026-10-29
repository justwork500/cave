import asyncio
import json
from datetime import datetime, timedelta

import pytest

from cave.access.items import get_item, upsert_item
from cave.automation.manager import AutomationManager
from cave.config.store import ConfigStore
from cave.state import Entity, EventBus, StateMachine
from tests.engine_helpers import FakeEffects


class Clock:
    def __init__(self) -> None:
        self.t = datetime(2026, 1, 7, 6, 59)

    def __call__(self) -> datetime:
        return self.t


class FakeSleep:
    """sleep() that only returns when the test releases it."""

    def __init__(self) -> None:
        self.waiting: list[asyncio.Future[None]] = []

    async def __call__(self, seconds: float) -> None:
        fut: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self.waiting.append(fut)
        await fut

    def release(self) -> None:
        for f in self.waiting:
            if not f.done():
                f.set_result(None)
        self.waiting.clear()


class GatedEffects(FakeEffects):
    """delay actions wait for the test to open the gate."""

    def __init__(self) -> None:
        super().__init__()
        self.gate = asyncio.Event()
        self.started = 0

    async def sleep(self, seconds: float) -> None:
        self.started += 1
        await self.gate.wait()
        self.calls.append(("sleep", seconds))


async def settle() -> None:
    for _ in range(30):
        await asyncio.sleep(0)


def write(tmp_path, ident: str, text: str) -> None:
    folder = tmp_path / "automations"
    folder.mkdir(exist_ok=True)
    (folder / f"{ident}.yaml").write_text(text, encoding="utf-8")


def auto(ident: str, trigger: str, actions: str = "    - type: call\n      target: light.a\n      command: turn_on\n",
         extra: str = "") -> str:
    return (f"automation:\n  id: {ident}\n  name: {ident}\n{extra}  triggers:\n    - {trigger}\n"
            f"  actions:\n{actions}")


async def make(db, tmp_path, effects=None):
    bus = EventBus()
    states = StateMachine(bus)
    for e in ("light.a", "binary_sensor.door", "sensor.t"):
        states.register(Entity(e, e, None, e.split(".")[0]))
    store = ConfigStore(tmp_path, db, bus)
    store.load_all()
    clock, sleeper = Clock(), FakeSleep()
    fx = effects or FakeEffects()
    m = AutomationManager(store, db, states, bus, fx, now=clock, sleep=sleeper)
    await m.start()
    await settle()
    return m, states, fx, clock, sleeper


def calls(fx):
    return [c for c in fx.calls if c[0] == "call"]


def test_state_trigger_from_to(db, tmp_path):
    write(tmp_path, "door", auto("door", 'type: state\n      entity: binary_sensor.door\n      from: "off"\n      to: "on"'))

    async def go():
        m, states, fx, *_ = await make(db, tmp_path)
        states.set("binary_sensor.door", "on")  # from None: no match
        await settle()
        states.set("binary_sensor.door", "off")
        states.set("binary_sensor.door", "on")
        await settle()
        await m.stop()
        return fx

    assert len(calls(asyncio.run(go()))) == 1


def test_attribute_only_change_ignored(db, tmp_path):
    write(tmp_path, "t", auto("t", "type: state\n      entity: sensor.t"))

    async def go():
        m, states, fx, *_ = await make(db, tmp_path)
        states.set("sensor.t", "20")
        await settle()
        states.set("sensor.t", "20", {"unit": "C"})
        await settle()
        await m.stop()
        return fx

    assert len(calls(asyncio.run(go()))) == 1


def test_numeric_state_crossing_only(db, tmp_path):
    write(tmp_path, "hot", auto("hot", "type: numeric_state\n      entity: sensor.t\n      above: 25"))

    async def go():
        m, states, fx, *_ = await make(db, tmp_path)
        for v in ("20", "26", "27", "24", "30"):
            states.set("sensor.t", v)
            await settle()
        await m.stop()
        return fx

    assert len(calls(asyncio.run(go()))) == 2


def test_for_duration_fires_and_cancels(db, tmp_path):
    write(tmp_path, "held", auto("held", 'type: state\n      entity: binary_sensor.door\n      to: "on"\n      for: 120'))

    async def go():
        m, states, fx, _clock, sleeper = await make(db, tmp_path)
        states.set("binary_sensor.door", "on")
        await settle()
        states.set("binary_sensor.door", "off")  # back before two minutes: cancelled
        await settle()
        sleeper.release()
        await settle()
        first = len(calls(fx))
        states.set("binary_sensor.door", "on")
        await settle()
        sleeper.release()
        await settle()
        await m.stop()
        return first, len(calls(fx))

    assert asyncio.run(go()) == (0, 1)


def test_time_and_time_pattern(db, tmp_path):
    write(tmp_path, "seven", auto("seven", 'type: time\n      at: "07:00"'))
    write(tmp_path, "quarter", auto("quarter", 'type: time_pattern\n      minutes: "/15"'))

    async def go():
        m, _s, fx, clock, _ = await make(db, tmp_path)
        fired = []
        for minute in range(31):
            clock.t = datetime(2026, 1, 7, 7, 0) + timedelta(minutes=minute)
            await m.tick()
            await settle()
            fired.append(len(calls(fx)))
        await m.stop()
        return fired

    fired = asyncio.run(go())
    assert fired[0] == 2 and fired[15] == 3 and fired[30] == 4 and fired[29] == 3


def test_startup_trigger(db, tmp_path):
    write(tmp_path, "boot", auto("boot", "type: startup"))

    async def go():
        m, _s, fx, *_ = await make(db, tmp_path)
        await m.stop()
        return fx

    assert len(calls(asyncio.run(go()))) == 1


def test_conditions_not_met_trace(db, tmp_path):
    write(tmp_path, "c", auto("c", "type: startup", extra=(
        "  conditions:\n    - type: state\n      entity: light.a\n      state: \"on\"\n")))

    async def go():
        m, _s, fx, *_ = await make(db, tmp_path)
        await m.stop()
        return m, fx

    m, fx = asyncio.run(go())
    assert calls(fx) == [] and m.traces("automation:c")[0]["outcome"] == "conditions_not_met"


@pytest.mark.parametrize(("mode", "expected_runs", "expected_outcomes"), [
    ("single", 1, ["finished"]),
    ("restart", 4, ["cancelled", "cancelled", "cancelled", "finished"]),
    ("queued", 3, ["finished", "finished", "finished"]),
    ("parallel", 2, ["finished", "finished"]),
])
def test_run_modes(db, tmp_path, mode, expected_runs, expected_outcomes):  # Review Focus 3
    write(tmp_path, "m", auto("m", "type: state\n      entity: sensor.t",
                              actions="    - type: delay\n      duration: 1\n",
                              extra=f"  mode: {mode}\n  max: 2\n"))

    async def go():
        fx = GatedEffects()
        m, states, *_ = await make(db, tmp_path, fx)
        for v in ("1", "2", "3", "4"):
            states.set("sensor.t", v)
            await settle()
        fx.gate.set()
        for _ in range(5):
            await settle()
        await m.stop()
        return m

    m = asyncio.run(go())
    outcomes = [t["outcome"] for t in m.traces("automation:m")]
    assert len(outcomes) == expected_runs and sorted(outcomes) == sorted(expected_outcomes)


def test_traces_capped_at_20(db, tmp_path):
    write(tmp_path, "t", auto("t", "type: state\n      entity: sensor.t"))

    async def go():
        m, states, *_ = await make(db, tmp_path)
        for v in range(25):
            states.set("sensor.t", str(v))
            await settle()
        await m.stop()
        return m

    m = asyncio.run(go())
    rows = db.execute("SELECT count(*) FROM automation_traces WHERE item_id='automation:t'").fetchone()[0]
    assert rows == 20 and len(m.traces("automation:t")) == 20
    assert json.loads(db.execute("SELECT trace FROM automation_traces LIMIT 1").fetchone()[0])["steps"]


def test_disabled_automation_and_disabled_item_not_armed(db, tmp_path):
    write(tmp_path, "off", auto("off", "type: startup", extra="  enabled: false\n"))
    write(tmp_path, "item-off", auto("item-off", "type: startup"))

    async def go():
        bus = EventBus()
        store = ConfigStore(tmp_path, db, bus)
        store.load_all()
        item = get_item(db, "automation:item-off")
        upsert_item(db, "test", item.__class__(**{**item.__dict__, "status": "disabled"}))
        fx = FakeEffects()
        m = AutomationManager(store, db, StateMachine(bus), bus, fx, now=Clock(), sleep=FakeSleep())
        await m.start()
        await settle()
        await m.stop()
        return fx

    assert calls(asyncio.run(go())) == []


def test_rearm_after_save(db, tmp_path):
    async def go():
        m, states, fx, *_ = await make(db, tmp_path)
        write(tmp_path, "late", auto("late", "type: state\n      entity: sensor.t"))
        m.store.load_all()
        m.rearm()
        states.set("sensor.t", "5")
        await settle()
        await m.stop()
        return fx

    assert len(calls(asyncio.run(go()))) == 1
