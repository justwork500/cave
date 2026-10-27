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
MAX_ENTITIES = 5000


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


class MqttBridge:
    def __init__(self, db: Database, states: StateMachine, publish: Publish, prefix: str = "homeassistant") -> None:
        self.db = db
        self.states = states
        self._publish = publish
        self.prefix = prefix
        self._configs: dict[str, tuple[EntityConfig, str]] = {}  # unique_id -> (config, entity_id)
        self._by_entity: dict[str, str] = {}  # entity_id -> unique_id
        self._config_topics: dict[str, str] = {}  # discovery topic -> unique_id
        self._listeners: dict[str, set[str]] = {}  # state/availability topic -> unique_ids
        self._unsupported: dict[str, str] = {}  # topic -> reason

    def subscriptions(self) -> set[str]:
        return {f"{self.prefix}/+/+/config", f"{self.prefix}/+/+/+/config"} | set(self._listeners)

    async def handle(self, topic: str, payload: bytes) -> set[str]:
        """Process one message. Returns topics that now need subscribing to."""
        result = parse_config(topic, payload, self.prefix)
        if result is None:
            self._route(topic, payload)
            return set()
        if isinstance(result, Removal):
            uid = self._config_topics.pop(topic, None)
            if uid:
                self._remove(uid)
            return set()
        if isinstance(result, Unsupported):
            self._note_unsupported(result.topic, result.reason)
            return set()
        return self._register(result, topic)

    def add_manual(self, cfg: EntityConfig) -> set[str]:
        return self._register(cfg, None)

    async def publish(self, topic: str, payload: str, retain: bool = False) -> None:
        if not topic or "+" in topic or "#" in topic:
            raise ValueError("MQTT topics to publish to can't be empty or contain + or #.")
        await self._publish(topic, payload, retain)

    def status(self) -> dict[str, Any]:
        return {
            "entities": len(self._configs),
            "unsupported": [{"topic": t, "reason": r} for t, r in sorted(self._unsupported.items())],
        }

    # ---- internals ----

    def _note_unsupported(self, topic: str, reason: str) -> None:
        if self._unsupported.get(topic) != reason:
            log.info("MQTT %s: %s", topic, reason)
        self._unsupported[topic] = reason

    def _entity_id_for(self, cfg: EntityConfig) -> str:
        """Stable forever: the first id a unique_id gets is stored and reused."""
        row = self.db.execute("SELECT entity_id FROM mqtt_entities WHERE unique_id=?", (cfg.unique_id,)).fetchone()
        if row:
            return str(row["entity_id"])
        base = f"{cfg.component}.{_slug(cfg.name) or _slug(cfg.unique_id) or 'mqtt'}"
        taken = {r["entity_id"] for r in self.db.execute("SELECT entity_id FROM mqtt_entities").fetchall()}
        taken |= {e.entity_id for e in self.states.entities()}
        entity_id, n = base, 2
        while entity_id in taken:
            entity_id, n = f"{base}_{n}", n + 1
        self.db.execute(
            "INSERT INTO mqtt_entities (unique_id, entity_id, first_seen) VALUES (?, ?, ?)",
            (cfg.unique_id, entity_id, datetime.now(UTC).isoformat()),
        )
        return entity_id

    def _register(self, cfg: EntityConfig, config_topic: str | None) -> set[str]:
        known = self._configs.get(cfg.unique_id)
        if known is None and len(self._configs) >= MAX_ENTITIES:
            self._note_unsupported(config_topic or cfg.unique_id, "too many MQTT entities")
            return set()
        before = set(self._listeners)
        if known is not None:
            self._unlisten(cfg.unique_id, known[0])
        entity_id = known[1] if known else self._entity_id_for(cfg)
        self.states.register(Entity(entity_id, cfg.name, None, cfg.component))
        self.states.set_entity_handler(entity_id, self._handler)
        self._configs[cfg.unique_id] = (cfg, entity_id)
        self._by_entity[entity_id] = cfg.unique_id
        if config_topic:
            self._config_topics[config_topic] = cfg.unique_id
        for t in topics_for(cfg):
            self._listeners.setdefault(t, set()).add(cfg.unique_id)
        return set(self._listeners) - before

    def _unlisten(self, uid: str, cfg: EntityConfig) -> None:
        for t in topics_for(cfg):
            ids = self._listeners.get(t)
            if ids is not None:
                ids.discard(uid)
                if not ids:
                    del self._listeners[t]

    def _remove(self, uid: str) -> None:
        known = self._configs.pop(uid, None)
        if known is None:
            return
        cfg, entity_id = known
        self._unlisten(uid, cfg)
        self._by_entity.pop(entity_id, None)
        self.states.remove(entity_id)

    def _route(self, topic: str, payload: bytes) -> None:
        for uid in list(self._listeners.get(topic, ())):
            cfg, entity_id = self._configs[uid]
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
        uid = self._by_entity.get(entity_id)
        if uid is None:
            raise KeyError(entity_id)
        cfg = self._configs[uid][0]
        if command == "toggle":
            current = self.states.get(entity_id)
            command = "turn_off" if current is not None and current.value == "on" else "turn_on"
        for t, p in command_to_publish(cfg, command, args):
            await self._publish(t, p, False)
