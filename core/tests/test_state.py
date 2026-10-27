import asyncio

import pytest

from cave.state import Entity, EventBus, StateMachine


def make() -> tuple[EventBus, StateMachine]:
    bus = EventBus()
    sm = StateMachine(bus)
    sm.register(Entity("light.kitchen", "Kitchen light", "kitchen", "light"))
    return bus, sm


def test_set_publishes_state_changed():
    bus, sm = make()
    q = bus.subscribe()
    sm.set("light.kitchen", "on", {"brightness": 180})
    e = q.get_nowait()
    assert e == {"type": "state_changed", "entity_id": "light.kitchen", "old": None, "new": "on",
                 "attributes": {"brightness": 180}}
    bus.unsubscribe(q)
    sm.set("light.kitchen", "off")
    assert q.empty()


def test_last_changed_only_moves_on_value_change():
    _, sm = make()
    first = sm.set("light.kitchen", "on")
    again = sm.set("light.kitchen", "on", {"brightness": 10})
    assert again.last_changed == first.last_changed and again.last_updated >= first.last_updated
    assert sm.set("light.kitchen", "off").last_changed >= first.last_changed


def test_entity_id_must_have_known_capability():
    _, sm = make()
    with pytest.raises(ValueError):
        sm.register(Entity("garage", "Garage", None, "garage"))
    with pytest.raises(ValueError):
        sm.register(Entity("teleporter.one", "T", None, "teleporter"))


def test_set_unknown_entity_raises():
    _, sm = make()
    with pytest.raises(KeyError):
        sm.set("light.nope", "on")


def test_remove_drops_entity_and_state():
    _, sm = make()
    sm.set("light.kitchen", "on")
    sm.remove("light.kitchen")
    assert sm.get("light.kitchen") is None and sm.entities() == []


def test_command_routes_to_capability_handler():
    _, sm = make()
    calls = []

    async def handler(entity_id, command, args):
        calls.append((entity_id, command, args))

    sm.set_command_handler("light", handler)
    asyncio.run(sm.command("light.kitchen", "turn_on", {"brightness": 5}))
    assert calls == [("light.kitchen", "turn_on", {"brightness": 5})]


def test_command_without_handler_raises():
    _, sm = make()
    with pytest.raises(KeyError):
        asyncio.run(sm.command("light.kitchen", "turn_on", {}))


def test_entity_handler_overrides_capability_handler():
    _, sm = make()
    calls = []

    async def cap(entity_id, command, args):
        calls.append("capability")

    async def ent(entity_id, command, args):
        calls.append("entity")

    sm.set_command_handler("light", cap)
    sm.set_entity_handler("light.kitchen", ent)
    asyncio.run(sm.command("light.kitchen", "turn_on", {}))
    sm.set_entity_handler("light.kitchen", None)
    asyncio.run(sm.command("light.kitchen", "turn_on", {}))
    assert calls == ["entity", "capability"]


def test_remove_clears_entity_handler():
    _, sm = make()

    async def ent(entity_id, command, args): ...

    sm.set_entity_handler("light.kitchen", ent)
    sm.remove("light.kitchen")
    sm.register(Entity("light.kitchen", "Kitchen light", "kitchen", "light"))
    with pytest.raises(KeyError):
        asyncio.run(sm.command("light.kitchen", "turn_on", {}))
