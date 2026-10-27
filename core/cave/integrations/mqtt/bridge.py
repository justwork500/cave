"""MqttBridge: broker messages in, registry entries and state out; CAVE commands in, publishes out."""

import logging
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from cave.db import Database
from cave.integrations.mqtt.discovery import EntityConfig, Removal, Unsupported, parse_config
from cave.integrations.mqtt.mapping import command_to_publish, state_from_message, topics_for
from cave.state import Entity, StateMachine

log = logging.getLogger(__name__)

Publish = Callable[[str, str, bool], Awaitable[None]]
MAX_ENTITIES = 5000  # also caps the stored id map, so add/remove cycles can't grow it either
MAX_UNSUPPORTED = 200
MAX_SLUG = 64
MANUAL = "manual"
Key = tuple[str, str]  # (component, unique_id): the same id announced as another type is another entity


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:MAX_SLUG].rstrip("_")


def _key(cfg: EntityConfig) -> Key:
    return cfg.component, cfg.unique_id


class MqttBridge:
    def __init__(self, db: Database, states: StateMachine, publish: Publish, prefix: str = "homeassistant") -> None:
        self.db = db
        self.states = states
        self._publish = publish
        self.prefix = prefix
        self._configs: dict[Key, tuple[EntityConfig, str]] = {}  # key -> (config, entity_id)
        self._by_entity: dict[str, Key] = {}
        self._config_topics: dict[str, Key] = {}  # discovery topic -> key
        self._listeners: dict[str, set[Key]] = {}  # state/availability topic -> keys
        self._unsupported: dict[str, str] = {}  # topic -> reason, oldest first

    def subscriptions(self) -> set[str]:
        return {f"{self.prefix}/+/+/config", f"{self.prefix}/+/+/+/config"} | set(self._listeners)

    async def handle(self, topic: str, payload: bytes) -> set[str]:
        """Process one message. Returns topics that now need subscribing to."""
        result = parse_config(topic, payload, self.prefix)
        if result is None:
            self._route(topic, payload)
            return set()
        if isinstance(result, Removal):
            key = self._config_topics.pop(topic, None)
            if key:
                self._remove(key)
            return set()
        if isinstance(result, Unsupported):
            self._note_unsupported(result.topic, result.reason)
            return set()
        return self._register(result, topic)

    def add_manual(self, cfg: EntityConfig) -> set[str]:
        return self._register(cfg, MANUAL)

    async def publish(self, topic: str, payload: str, retain: bool = False) -> None:
        if not topic or "+" in topic or "#" in topic:
            raise ValueError("MQTT topics to publish to can't be empty or contain + or #.")
        await self._publish(topic, payload, retain)

    def status(self) -> dict[str, Any]:
        return {
            "entities": len(self._configs),
            "unsupported": [{"topic": t, "reason": r} for t, r in self._unsupported.items()],
        }

    # ---- internals ----

    def _note_unsupported(self, topic: str, reason: str) -> None:
        if self._unsupported.get(topic) == reason:
            return
        log.info("MQTT %s: %s", topic, reason)
        self._unsupported.pop(topic, None)
        self._unsupported[topic] = reason
        while len(self._unsupported) > MAX_UNSUPPORTED:
            del self._unsupported[next(iter(self._unsupported))]

    def _binding(self, cfg: EntityConfig) -> tuple[str, str] | None:
        """(entity_id, config_topic) stored for this device, if it has been seen before."""
        row = self.db.execute(
            "SELECT entity_id, config_topic FROM mqtt_entities WHERE component=? AND unique_id=?", _key(cfg)
        ).fetchone()
        return (str(row["entity_id"]), str(row["config_topic"])) if row else None

    def _new_entity_id(self, cfg: EntityConfig, source: str) -> str | None:
        """Stored forever: the first id a device gets is reused every time it comes back."""
        if self.db.execute("SELECT count(*) FROM mqtt_entities").fetchone()[0] >= MAX_ENTITIES:
            return None
        base = f"{cfg.component}.{_slug(cfg.name) or _slug(cfg.unique_id) or 'mqtt'}"
        taken = {r["entity_id"] for r in self.db.execute("SELECT entity_id FROM mqtt_entities").fetchall()}
        taken |= {e.entity_id for e in self.states.entities()}
        entity_id, n = base, 2
        while entity_id in taken:
            entity_id, n = f"{base}_{n}", n + 1
        self.db.execute(
            "INSERT INTO mqtt_entities (component, unique_id, entity_id, config_topic, first_seen) "
            "VALUES (?, ?, ?, ?, ?)",
            (cfg.component, cfg.unique_id, entity_id, source, datetime.now(UTC).isoformat()),
        )
        return entity_id

    def _register(self, cfg: EntityConfig, source: str) -> set[str]:
        """source is the discovery topic, or MANUAL. A device stays bound to the source that first announced it."""
        key = _key(cfg)
        bound = self._binding(cfg)
        if bound is not None and bound[1] != source:
            # Someone else announcing an existing device would otherwise redirect its commands.
            why = "set in mqtt.yaml" if bound[1] == MANUAL else "announced on another discovery topic"
            self._note_unsupported(source, f"unique_id {cfg.unique_id!r} is already {why}")
            return set()
        entity_id = bound[0] if bound else self._new_entity_id(cfg, source)
        if entity_id is None:
            self._note_unsupported(source, "too many MQTT entities")
            return set()
        before = set(self._listeners)
        known = self._configs.get(key)
        if known is not None:
            self._unlisten(key, known[0])
        self.states.register(Entity(entity_id, cfg.name, None, cfg.component))
        self.states.set_entity_handler(entity_id, self._handler)
        self._configs[key] = (cfg, entity_id)
        self._by_entity[entity_id] = key
        if source != MANUAL:
            self._config_topics[source] = key
        for t in topics_for(cfg):
            self._listeners.setdefault(t, set()).add(key)
        return set(self._listeners) - before

    def _unlisten(self, key: Key, cfg: EntityConfig) -> None:
        for t in topics_for(cfg):
            keys = self._listeners.get(t)
            if keys is not None:
                keys.discard(key)
                if not keys:
                    del self._listeners[t]

    def _remove(self, key: Key) -> None:
        known = self._configs.pop(key, None)
        if known is None:
            return
        cfg, entity_id = known
        self._unlisten(key, cfg)
        self._by_entity.pop(entity_id, None)
        self.states.remove(entity_id)

    def _route(self, topic: str, payload: bytes) -> None:
        for key in list(self._listeners.get(topic, ())):
            cfg, entity_id = self._configs[key]
            current = self.states.get(entity_id)
            new = state_from_message(
                cfg, topic, payload, (current.value, dict(current.attributes)) if current else None
            )
            if new is None:
                continue
            value, attrs = new
            if cfg.device:
                attrs = {**attrs, "device": dict(cfg.device)}
            # shortcut: device info lives on entity attributes until a device registry exists (console plan)
            self.states.set(entity_id, value, attrs)

    async def _handler(self, entity_id: str, command: str, args: dict[str, Any]) -> None:
        key = self._by_entity.get(entity_id)
        if key is None:
            raise KeyError(entity_id)
        cfg = self._configs[key][0]
        if command == "toggle":
            current = self.states.get(entity_id)
            command = "turn_off" if current is not None and current.value == "on" else "turn_on"
        for t, p in command_to_publish(cfg, command, args):
            await self._publish(t, p, False)
