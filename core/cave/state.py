import asyncio
import logging
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

log = logging.getLogger(__name__)

Event = dict[str, Any]
CommandHandler = Callable[[str, str, dict[str, Any]], Awaitable[None]]

CAPABILITIES = frozenset({
    "light", "switch", "fan", "cover", "lock", "climate", "media_player", "button", "number", "select", "scene",
    "sensor", "binary_sensor", "device_tracker", "weather", "camera", "update", "event",
    "notify", "script", "automation",
})
_ENTITY_ID = re.compile(r"^([a-z_]+)\.([a-z0-9_]+)$")
QUEUE_SIZE = 1000
OVERFLOW: Event = {"type": "overflow"}


@dataclass(frozen=True)
class Entity:
    entity_id: str
    name: str
    area_id: str | None
    capability: str


@dataclass(frozen=True)
class State:
    entity_id: str
    value: str
    attributes: Mapping[str, Any]
    last_changed: datetime
    last_updated: datetime


class EventBus:
    """Fan-out to subscriber queues. Safe to publish from any thread (sync API routes run in a thread pool)."""

    def __init__(self) -> None:
        self._subs: list[tuple[asyncio.AbstractEventLoop | None, asyncio.Queue[Event]]] = []

    def subscribe(self) -> "asyncio.Queue[Event]":
        try:
            loop: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        q: asyncio.Queue[Event] = asyncio.Queue(QUEUE_SIZE)
        self._subs.append((loop, q))
        return q

    def unsubscribe(self, q: "asyncio.Queue[Event]") -> None:
        self._subs = [(loop, sq) for loop, sq in self._subs if sq is not q]

    def publish(self, event: Event) -> None:
        try:
            current: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
        except RuntimeError:
            current = None
        for loop, q in list(self._subs):
            if loop is None or loop is current:
                _put(q, event)
            elif not loop.is_closed():
                loop.call_soon_threadsafe(_put, q, event)


def _put(q: "asyncio.Queue[Event]", event: Event) -> None:
    try:
        q.put_nowait(event)
    except asyncio.QueueFull:
        # A subscriber this far behind can't be trusted to see access changes; replace its backlog with a
        # marker so it resyncs (the WebSocket closes and the client reconnects with fresh access).
        log.warning("event queue full; subscriber must resync")
        while not q.empty():
            q.get_nowait()
        q.put_nowait(OVERFLOW)


@dataclass
class StateMachine:
    bus: EventBus
    _entities: dict[str, Entity] = field(default_factory=dict)
    _states: dict[str, State] = field(default_factory=dict)
    _handlers: dict[str, CommandHandler] = field(default_factory=dict)

    def register(self, entity: Entity) -> None:
        m = _ENTITY_ID.match(entity.entity_id)
        if not m or m.group(1) not in CAPABILITIES or m.group(1) != entity.capability:
            raise ValueError(f"Invalid entity id {entity.entity_id!r}")
        self._entities[entity.entity_id] = entity

    def remove(self, entity_id: str) -> None:
        self._entities.pop(entity_id, None)
        self._states.pop(entity_id, None)

    def entities(self) -> list[Entity]:
        return list(self._entities.values())

    def entity(self, entity_id: str) -> Entity | None:
        return self._entities.get(entity_id)

    def get(self, entity_id: str) -> State | None:
        return self._states.get(entity_id)

    def set(self, entity_id: str, value: str, attributes: Mapping[str, Any] | None = None) -> State:
        if entity_id not in self._entities:
            raise KeyError(entity_id)
        now = datetime.now(UTC)
        old = self._states.get(entity_id)
        last_changed = old.last_changed if old is not None and old.value == value else now
        state = State(entity_id, value, dict(attributes or {}), last_changed, now)
        self._states[entity_id] = state
        self.bus.publish({
            "type": "state_changed",
            "entity_id": entity_id,
            "old": old.value if old else None,
            "new": value,
            "attributes": dict(state.attributes),
        })
        return state

    def set_command_handler(self, capability: str, handler: CommandHandler) -> None:
        self._handlers[capability] = handler

    async def command(self, entity_id: str, command: str, args: dict[str, Any]) -> None:
        entity = self._entities[entity_id]
        await self._handlers[entity.capability](entity_id, command, args)
