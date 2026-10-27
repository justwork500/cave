# CAVE Phase 1 · Plan 3: MQTT — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Devices on an MQTT broker show up in CAVE by themselves and can be controlled through the access model. That covers Zigbee2MQTT, Tasmota, Shelly and ESPHome in MQTT mode, plus hand-written MQTT entities for devices that don't announce themselves.

**Architecture:** The MQTT code is split into three parts:
- **Pure translation, no network:** discovery parsing, state mapping, command mapping and value templates. These are tested with real device payloads as fixtures.
- **`MqttBridge`:** owns the entities. It turns broker messages into registry entries and state, and turns CAVE commands into publishes, through an injected `publish` function.
- **A thin `aiomqtt` transport:** connects, reconnects with backoff and feeds the bridge. It runs inside the app's lifespan, and only when `config/mqtt.yaml` exists.

Discovered entities start inside no item, so the access model keeps them Admin-only until an Admin puts them on a dashboard.

**Tech Stack:** Python 3.13, `aiomqtt` 2.x (new: the async MQTT client the framework names), `jinja2` (new: discovery `value_template`s are Jinja; it's rendered in `ImmutableSandboxedEnvironment`, which the framework already chose for templates), Pydantic v2, PyYAML.

**Spec:** `docs/superpowers/specs/2026-10-25-cave-phase1-design.md`, section "Devices: MQTT" and the scope table row "Devices". Background: the framework's integration catalog row "MQTT". This builds on Plans 1 and 2, both on `main`.

## Global Constraints

- Everything in Plans 1 and 2's Global Constraints still holds.
- Discovery topic format: `<prefix>/<component>/[<node_id>/]<object_id>/config`, with prefix default `homeassistant`. This is an open protocol used by Zigbee2MQTT, Tasmota, Shelly and ESPHome. CAVE copies no Home Assistant code and uses no HA branding.
- Components mapped in Phase 1, exactly: `light`, `switch`, `sensor`, `binary_sensor`, `cover`, `lock`, `button`. Anything else is listed as "unsupported" in the MQTT status, never half-mapped.
- An empty retained config payload removes the entity.
- Entity IDs stay **stable across restarts and re-discovery**. Automations and dashboards reference them.
- Broker credentials: host, port and username go in `config/mqtt.yaml`. The password comes from the environment variable `CAVE_MQTT_PASSWORD`, never a config file (config is meant to be committed to Git).
- MQTT payloads are **untrusted input**:
  - config payloads are capped at 64 KiB, state payloads at 256 KiB
  - templates are capped at 2,000 characters and rendered in the sandbox
  - command topics may not contain `+` or `#`
  - at most 5,000 MQTT entities
- Tests never open a network connection. A live-broker test runs only when `CAVE_MQTT_TEST_BROKER` is set.

## Review Focus

1. **Retained discovery configs replayed after a reconnect or restart** → the same entity IDs come back, with no duplicates (`light.kitchen_lamp`, not `light.kitchen_lamp_2`). Pinned in Task 3.
2. **A discovery config with a wildcard, empty or missing command topic on a controllable component** → that entity is refused or made read-only, and nothing is ever published to a wildcard topic. Pinned in Task 1.
3. **A hostile or broken `value_template`** (`{{ ''.__class__.__mro__ }}`, `{{ range(10**9)|list }}`, a syntax error) → rendering fails safe: the state is left unchanged, the error is logged once, and nothing crashes. Pinned in Task 2.
4. **A state message for a topic whose entity was removed, or arrives before its config** → ignored. Pinned in Task 3.
5. **Non-UTF-8 or non-JSON payloads where JSON is expected** → ignored with a log line, and the last good state is kept. Pinned in Task 2.

---

## File structure

```text
core/cave/templates.py                         # sandboxed Jinja for value templates
core/cave/integrations/__init__.py
core/cave/integrations/mqtt/__init__.py
core/cave/integrations/mqtt/discovery.py       # topic + payload -> EntityConfig (pure)
core/cave/integrations/mqtt/mapping.py         # MQTT message <-> CAVE state/command (pure)
core/cave/integrations/mqtt/bridge.py          # MqttBridge: registry, state, commands, publish
core/cave/integrations/mqtt/config.py          # config/mqtt.yaml loader (broker + manual entities)
core/cave/integrations/mqtt/client.py          # aiomqtt transport, reconnect, status
core/cave/migrations/0003_mqtt.sql             # stable unique_id -> entity_id map
core/cave/state.py                             # per-entity command handlers
core/cave/api/app.py                           # lifespan starts MQTT when configured
core/cave/api/system.py                        # GET /api/v1/system/mqtt
core/tests/fixtures/mqtt/*.json                # real-world discovery payloads
deploy/mosquitto/mosquitto.conf
docs/integrations/mqtt.md
```

---

### Task 1: Discovery parsing

**Files:**
- Create: `core/cave/integrations/__init__.py`, `core/cave/integrations/mqtt/__init__.py`, `core/cave/integrations/mqtt/discovery.py`, and fixtures `core/tests/fixtures/mqtt/{z2m_light_json.json, z2m_contact.json, tasmota_switch.json, shelly_cover.json, esphome_sensor.json, z2m_lock.json, button.json}`
- Modify: `core/pyproject.toml` (add `aiomqtt>=2.3`, `jinja2>=3.1`)
- Test: `core/tests/test_mqtt_discovery.py`

**Interfaces:**
- Produces:
  - `Component = Literal["light", "switch", "sensor", "binary_sensor", "cover", "lock", "button"]`
  - `@dataclass(frozen=True) class EntityConfig`, with fields:
    - `component: Component`, `unique_id: str` (the payload's `unique_id`, else `"<node_id>_<object_id>"` from the topic)
    - `name: str` (device name + entity name, falling back to `object_id`)
    - `state_topic: str | None`, `command_topic: str | None`, `value_template: str | None`
    - `json_schema: bool` (light `schema: json`)
    - `payload_on: str`, `payload_off: str`, `state_on: str`, `state_off: str`
    - `payload_open: str`, `payload_close: str`, `payload_stop: str`, `state_open: str`, `state_closed: str`, `state_opening: str`, `state_closing: str`
    - `payload_lock: str`, `payload_unlock: str`, `state_locked: str`, `state_unlocked: str`, `payload_press: str`
    - `brightness: bool`, `brightness_scale: int`, `brightness_state_topic: str | None`, `brightness_command_topic: str | None`
    - `unit: str | None`, `device_class: str | None`
    - `availability: tuple[tuple[str, str, str], ...]` (topic, available payload, not-available payload)
    - `device: Mapping[str, str]` (name, manufacturer, model, sw_version, when given)
    - `read_only: bool`

    Defaults are the protocol's usual ones: `ON`/`OFF`; `OPEN`/`CLOSE`/`STOP`; `open`/`closed`/`opening`/`closing`; `LOCK`/`UNLOCK`; `LOCKED`/`UNLOCKED`; `PRESS`; `online`/`offline`; brightness scale `255`.
  - `@dataclass(frozen=True) class Removal: unique_id: str`, and `@dataclass(frozen=True) class Unsupported: topic: str; reason: str`
  - `parse_topic(topic: str, prefix: str) -> tuple[str, str | None, str] | None` — `(component, node_id, object_id)`, or `None` if the topic isn't a config topic under `prefix`.
  - `parse_config(topic: str, payload: bytes, prefix: str) -> EntityConfig | Removal | Unsupported | None`. In order:
    1. A non-config topic → `None`.
    2. Over 64 KiB → `Unsupported`.
    3. Empty payload → `Removal`.
    4. Non-UTF-8 or non-JSON → `Unsupported`.
    5. A component outside the seven → `Unsupported("component not supported in this version")`.
    6. Expand abbreviations, then substitute `~`.
    7. Light `schema` other than `default`/`json` → `Unsupported`.
    8. A `command_topic` with `+` or `#`: a light, switch, cover or lock becomes read-only, a button becomes `Unsupported`.
    9. A template over 2,000 characters → `Unsupported`.
  - `ABBREVIATIONS: Mapping[str, str]` — the abbreviation table, limited to keys this plan reads, for example `stat_t → state_topic`, `cmd_t → command_topic`, `val_tpl → value_template`, `uniq_id → unique_id`, `avty_t → availability_topic`, `avty → availability`, `pl_on → payload_on`, `pl_off → payload_off`, `stat_on → state_on`, `stat_off → state_off`, `pl_avail → payload_available`, `pl_not_avail → payload_not_available`, `dev → device`, `unit_of_meas → unit_of_measurement`, `dev_cla → device_class`, `bri_stat_t`, `bri_cmd_t`, `bri_scl`, `pl_open`, `pl_cls`, `pl_stop`, `stat_open`, `stat_clsd`, `pl_lock`, `pl_unlk`, `stat_locked`, `stat_unlocked`, `pl_prs`. Inside `device`: `name`, `mf → manufacturer`, `mdl → model`, `sw → sw_version`. `~` is replaced only at the start or end of a topic value, as the protocol defines.

- [ ] **Step 1: Write the fixtures.** Each is a realistic payload in its device's own style:
  - Zigbee2MQTT JSON-schema light with brightness and an availability list
  - Zigbee2MQTT door contact as a `binary_sensor` with `value_template: "{{ value_json.contact }}"`, `payload_on: false` and `payload_off: true`. JSON booleans are compared as the rendered strings `"False"`/`"True"`, so the mapping must normalise them.
  - Tasmota switch using abbreviations and `~`
  - Shelly cover
  - ESPHome sensor with unit and device class
  - Zigbee2MQTT lock
  - a plain button
- [ ] **Step 2: Write failing tests:**
  - `test_parse_topic_with_and_without_node`
  - `test_z2m_light_json_schema` (component, `json_schema`, `brightness`, availability topic, device name)
  - `test_tasmota_abbreviations_and_tilde` (topics expanded from `~`)
  - `test_unique_id_falls_back_to_topic`
  - `test_empty_payload_is_removal`
  - `test_unsupported_component` (`climate`)
  - `test_unsupported_light_schema` (`template`)
  - `test_wildcard_command_topic_makes_read_only` (Review Focus 2: a switch with `cmd_t: "a/+/set"` becomes `read_only`; a button with `#` becomes `Unsupported`)
  - `test_oversize_and_non_json_unsupported`
  - `test_long_template_unsupported`
- [ ] **Step 3:** Run `cd core && ../.venv/Scripts/python -m pytest -q tests/test_mqtt_discovery.py`. Expected: FAIL.
- [ ] **Step 4:** Install the two new dependencies, then implement.
- [ ] **Step 5:** Rerun, then the full suite with `-W error`, `ruff check .` and `mypy --strict cave`. Expected: PASS.
- [ ] **Step 6: Commit** `git commit -s -m "feat(mqtt): discovery config parsing"`

---

### Task 2: Value templates and message mapping

**Files:**
- Create: `core/cave/templates.py`, `core/cave/integrations/mqtt/mapping.py`
- Test: `core/tests/test_templates.py`, `core/tests/test_mqtt_mapping.py`

**Interfaces:**
- Produces in `templates.py`: `class TemplateError(Exception)`; `render_value(template: str, payload: str) -> str`. It uses one module-level `ImmutableSandboxedEnvironment(autoescape=False, undefined=StrictUndefined)`, with variables `value` (the payload string) and `value_json` (the parsed JSON, or undefined when the payload isn't JSON). Every Jinja exception, including `SecurityError` and `UndefinedError`, becomes `TemplateError`. Compiled templates are cached by source text, up to 512 entries. The sandbox's built-in range limit (`MAX_RANGE`) stays as it is.
- Produces in `mapping.py`:
  - `topics_for(cfg: EntityConfig) -> set[str]` — every topic the bridge must subscribe to for this entity (state, brightness state, availability).
  - `state_from_message(cfg, topic: str, payload: bytes, current: tuple[str, dict[str, Any]] | None) -> tuple[str, dict[str, Any]] | None` — the new `(value, attributes)`, or `None` to leave the state unchanged.
    - Over 256 KiB, non-UTF-8, a template error, or non-JSON for a JSON-schema light → `None`.
    - Availability topic: a not-available payload → `("unavailable", attrs)`; an available payload → keep the current value (or `"unknown"`).
    - `switch`/`light`/`binary_sensor`: compare the rendered value case-sensitively with `state_on`/`payload_on` and `state_off`/`payload_off`. `"True"`/`"False"` from rendered JSON booleans also match `true`/`false` payloads. The result is `"on"`/`"off"`, and anything else gives `None`.
    - JSON-schema light: `state` gives on/off, and `brightness` is scaled to 0–255 and stored as attribute `brightness`.
    - `cover`: `open`, `closed`, `opening`, `closing`.
    - `lock`: `locked`, `unlocked`.
    - `sensor`: the rendered value as it is, with attributes `unit_of_measurement` and `device_class` when given.
    - `button`: always `None`.
  - `class CommandError(ValueError)`
  - `command_to_publish(cfg, command: str, args: dict[str, Any]) -> list[tuple[str, str]]` — the `(topic, payload)` pairs to publish. It raises `CommandError` for a read-only entity, an unknown command, or a bad argument (brightness outside 0–255, or not an int). The commands:
    - `switch`: `turn_on`, `turn_off`
    - `light`: `turn_on(brightness?)`, `turn_off`. The JSON schema sends one JSON object `{"state": "ON", "brightness": <scaled>}`. The default schema sends the payload, then the brightness to its own topic.
    - `cover`: `open`, `close`, `stop`
    - `lock`: `lock`, `unlock`
    - `button`: `press`

    `toggle` is resolved by the bridge, not here, because only the bridge knows the current state.

- [ ] **Step 1: Write failing tests**
  - `test_templates.py`:
    - `test_value_json_path`
    - `test_filters_float_round` (`{{ value_json.t | float | round(1) }}`)
    - `test_tasmota_brackets` (`{{ value_json['ENERGY']['Power'] }}`)
    - `test_sandbox_blocks_dunder` (Review Focus 3)
    - `test_huge_range_refused` (Review Focus 3: `TemplateError`, returns quickly)
    - `test_syntax_error_is_template_error`
    - `test_value_json_undefined_for_non_json`
  - `test_mqtt_mapping.py`, one per fixture:
    - `test_z2m_light_state_and_brightness`
    - `test_z2m_contact_boolean_payloads` (`{"contact": false}` → `"on"`, door open)
    - `test_tasmota_switch_on_off`
    - `test_cover_states`
    - `test_lock_states`
    - `test_sensor_value_and_unit`
    - `test_availability_offline_then_online_keeps_value`
    - `test_bad_payloads_keep_state` (Review Focus 5: non-UTF-8, non-JSON for the JSON light, oversize → `None`)
    - `test_commands_per_component` (exact topic and payload pairs, including the JSON light's `{"state": "ON", "brightness": 128}` with scale 255, and the default-schema light's two publishes)
    - `test_read_only_and_bad_args_raise`
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Rerun, then the full suite. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "feat(mqtt): sandboxed value templates and state/command mapping"`

---

### Task 3: The bridge

**Files:**
- Create: `core/cave/migrations/0003_mqtt.sql`, `core/cave/integrations/mqtt/bridge.py`
- Modify: `core/cave/state.py`
- Test: `core/tests/test_mqtt_bridge.py`, `core/tests/test_state.py` (extend)

**Interfaces:**
- Table in `0003`: `mqtt_entities(unique_id TEXT PRIMARY KEY, entity_id TEXT NOT NULL UNIQUE, first_seen TEXT NOT NULL)`. Rows are never deleted on removal, so an ID comes back if the device does.
- Modifies `state.py`: `StateMachine.set_entity_handler(entity_id: str, handler: CommandHandler | None) -> None` (`None` clears it). `command()` uses the entity handler first, then the capability handler. This lets future integrations share a capability such as `light` without clashing. `remove()` also clears the entity handler.
- Produces in `bridge.py`:
  - `Publish = Callable[[str, str, bool], Awaitable[None]]`, called with `(topic, payload, retain)`
  - `MAX_ENTITIES = 5000`
  - `class MqttBridge(db: Database, states: StateMachine, publish: Publish, prefix: str = "homeassistant")`, with:
    - `subscriptions() -> set[str]`: `<prefix>/+/+/config`, `<prefix>/+/+/+/config`, plus every `topics_for` of known entities.
    - `async handle(topic: str, payload: bytes) -> set[str]`: processes one message and returns **new** topics to subscribe to.
      - A config gives an `EntityConfig`: register, or update in place when the `unique_id` is known.
      - A `Removal` removes the entity from the state machine.
      - An `Unsupported` is recorded once per topic.
      - Anything else is routed to every entity listening on that topic, through `state_from_message`.
    - `add_manual(cfg: EntityConfig) -> set[str]`: the same as a discovered config (used by Task 4).
    - `async publish(topic: str, payload: str, retain: bool = False) -> None`: the `mqtt.publish` action Plan 4 will call. It rejects `+`/`#` with `ValueError`.
    - `status() -> dict[str, Any]`: `{"entities": int, "unsupported": [{"topic", "reason"}]}`.
  - Entity IDs: `<component>.<slug>`, where `slug` is the lowercased name with every run of non-`[a-z0-9]` characters turned into `_`, trimmed, and falling back to the slugified unique_id. On collision with another `unique_id`, append `_2`, `_3` and so on. The first assignment is stored in `mqtt_entities` and reused for good after that (Review Focus 1). `Entity.name` is the display name and `area_id` is `None`.
  - Each entity gets `set_entity_handler`. The handler maps `toggle` to `turn_off` or `turn_on` from the current state, calls `command_to_publish`, then awaits `publish` for each pair. A `CommandError` propagates as `ValueError`. (The REST and WS command paths already turn exceptions into errors. Make sure `ValueError` becomes `409 {"detail": <message>}` on REST and `success: false` on WS.)
  - Device info goes into the entity's attributes as `device` (name, manufacturer, model). `shortcut: device info lives on entity attributes until a device registry exists (console plan)`.

- [ ] **Step 1: Write failing tests**, with a `FakePublisher` that records calls:
  - `test_discovered_light_registers_and_takes_state` (feed the Zigbee2MQTT config, then a state message → `light.<slug>` is `on`, with brightness)
  - `test_replayed_config_keeps_entity_id` (Review Focus 1: feed it twice, then build a new bridge on the same DB and feed it again → the same ID, no `_2`)
  - `test_name_collision_gets_suffix`
  - `test_removal_removes_entity_and_ignores_later_state` (Review Focus 4)
  - `test_state_before_config_ignored` (Review Focus 4)
  - `test_command_publishes_via_handler` (`turn_on {brightness: 128}` → one publish to the command topic with the JSON payload)
  - `test_toggle_uses_current_state`
  - `test_read_only_command_rejected`
  - `test_publish_rejects_wildcards`
  - `test_entity_cap` (monkeypatch `MAX_ENTITIES = 2`; the third config → recorded as unsupported, "too many MQTT entities")
  - `test_discovered_entity_is_admin_only_until_on_an_item` (with the app fixture: register via the bridge; sam's `can_control` is False and the admin's is True)
  - `test_rest_command_on_read_only_is_409`
  - In `test_state.py`: `test_entity_handler_overrides_capability_handler` and `test_remove_clears_entity_handler`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement. Change the REST command route and the WS `_command` so that `ValueError` from a handler becomes 409 or `success: false`, carrying the message.
- [ ] **Step 4:** Rerun, then the full suite. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "feat(mqtt): bridge with stable entity ids and command publishing"`

---

### Task 4: `config/mqtt.yaml`

**Files:**
- Create: `core/cave/integrations/mqtt/config.py`
- Test: `core/tests/test_mqtt_config.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Broker: host: str; port: int = 1883; username: str | None = None; tls: bool = False`
  - `@dataclass(frozen=True) class MqttConfig: broker: Broker; discovery_prefix: str = "homeassistant"; entities: tuple[EntityConfig, ...] = ()`
  - `class ConfigError(ValueError)` — its message names the file and the key path, for example `mqtt.yaml: entities[2].command_topic: wildcards aren't allowed`
  - `load(path: Path) -> MqttConfig | None` — `None` when the file doesn't exist.
- File shape, validated with Pydantic models using `extra="forbid"`, so unknown keys fail:

  ```yaml
  broker:
    host: mosquitto
    port: 1883
    username: cave            # the password comes from CAVE_MQTT_PASSWORD
  discovery_prefix: homeassistant
  entities:
    - component: switch
      unique_id: garage_heater
      name: Garage heater
      state_topic: garage/heater/state
      command_topic: garage/heater/set
  ```

  Manual entities accept the same full (unabbreviated) keys as discovery and are built through the same code path as Task 1 (`parse_config`'s internal builder), so both behave identically.
- `shortcut: errors name the key path but not the line number; Plan 4's YAML loader adds line numbers for every config file`.

- [ ] **Step 1: Write failing tests:**
  - `test_missing_file_is_none`
  - `test_minimal_broker`
  - `test_manual_entity_equals_discovery_equivalent` (same `EntityConfig` as the matching discovery payload)
  - `test_unknown_key_rejected_with_path`
  - `test_password_key_rejected` (`broker.password:` → `ConfigError` telling the user to use `CAVE_MQTT_PASSWORD`)
  - `test_wildcard_command_topic_rejected`
  - `test_bad_yaml_is_config_error`
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Rerun, then the full suite. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "feat(mqtt): config/mqtt.yaml with manual entities"`

---

### Task 5: Transport, lifespan and status

**Files:**
- Create: `core/cave/integrations/mqtt/client.py`
- Modify: `core/cave/api/app.py` (FastAPI `lifespan`), `core/cave/api/system.py`
- Test: `core/tests/test_mqtt_client.py`

**Interfaces:**
- Produces in `client.py`:
  - `Status = Literal["disabled", "connecting", "connected", "failed"]`
  - `backoff(attempt: int) -> float` — `min(60, 2**attempt)` seconds: 1, 2, 4 … 60.
  - `class MqttService(cfg: MqttConfig, db, states, password: str | None)`, with:
    - `status: Status` and `last_error: str | None`, both readable
    - `bridge: MqttBridge`
    - `async run() -> None`: loop forever. Connect with `aiomqtt.Client(hostname, port, username, password, tls_params if tls)`, then subscribe to `bridge.subscriptions()`. Feed every message to `bridge.handle`, and subscribe to whatever topics it returns. On `aiomqtt.MqttError`, set `status="connecting"`, record `last_error`, and sleep `backoff(n)`. Authentication failures (return code 4 or 5) set `status="failed"` and still retry at 60 s.
    - `async stop() -> None`
  - Manual entities from the config are added to the bridge before the first connect.
- Produces in `app.py`: a `lifespan` that loads `settings.config_dir / "mqtt.yaml"`. When it's present, the lifespan starts `MqttService.run()` as a task and stores it in `app.state.mqtt`, then cancels it on shutdown. When it's absent, `app.state.mqtt = None`. A `ConfigError` is logged, and the app starts with MQTT `failed` and `last_error` set. The app never refuses to start over MQTT.
- Produces in `system.py`: `GET /api/v1/system/mqtt` (needs `section:devices` or `section:system`) → `{"status", "broker": "host:port" | null, "last_error", "entities", "unsupported": [...]}`.
- Windows note for local development: aiomqtt needs a selector event loop, and the Proactor loop that Windows uses by default can't run it. `cave serve` passes `loop="asyncio"` with `asyncio.SelectorEventLoop` on `win32` only. `shortcut: Windows is a dev convenience; Debian is the target`.

- [ ] **Step 1: Write failing tests:**
  - `test_backoff_schedule` (`[1, 2, 4, 8, 16, 32, 60, 60]`)
  - `test_status_disabled_without_config` (`GET /system/mqtt` → `{"status": "disabled", ...}`)
  - `test_bad_config_reports_failed` (write an invalid `mqtt.yaml` into the app's `config_dir`, run the lifespan with `with TestClient(app)` → `status == "failed"` and `last_error` names the key)
  - `test_service_feeds_bridge` (monkeypatch `aiomqtt.Client` with a fake async context manager that yields two messages, then raises `MqttError`; assert the entity exists, `status` went from connected to connecting, and the subscriptions included the config wildcards)
  - `test_live_broker_roundtrip`, marked to skip unless `CAVE_MQTT_TEST_BROKER=host:port`: it publishes a retained discovery config and a state, and sees the entity
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Rerun, then the full suite. Expected: PASS, with the live test skipped.
- [ ] **Step 5: Commit** `git commit -s -m "feat(mqtt): broker connection, reconnect and status"`

---

### Task 6: Mosquitto config and MQTT docs

**Files:**
- Create: `deploy/mosquitto/mosquitto.conf`, `docs/integrations/mqtt.md`
- Modify: `README.md` (one link)

- [ ] **Step 1:** Write `mosquitto.conf`: `listener 1883`, `allow_anonymous false`, `password_file /mosquitto/config/passwd`, `persistence true`, `persistence_location /mosquitto/data/`, `log_dest stdout`. Add a comment at the top saying Plan 7's installer creates the `cave` user and the passwd file, and that the port is published only on the LAN.
- [ ] **Step 2:** Write `docs/integrations/mqtt.md`, which covers:
  - what MQTT gives you
  - the supported components, and what each one shows and accepts, as a table
  - how Zigbee2MQTT, Tasmota, Shelly and ESPHome are set to send discovery messages (one line each, pointing at their own setting names)
  - a manual `mqtt.yaml` example
  - `CAVE_MQTT_PASSWORD`
  - **"New devices are Admin-only until you add them to a dashboard"**
  - why "unsupported" entries appear, and the MQTT status endpoint
- [ ] **Step 3: Commit** `git commit -s -m "docs: mqtt integration and mosquitto config"`

---

## Plan 3 done when

- CI is green: ruff, mypy --strict, pytest. The live-broker test is skipped without a broker.
- In tests, a Zigbee2MQTT-style light appears through discovery, keeps its entity ID across a restart, and toggles through `POST /api/v1/entities/{id}/commands/turn_on`, with the right payload published. Only once it's on a dashboard can a household member control it.
- A hostile template, a wildcard command topic or a garbage payload never crashes CAVE or publishes to a wildcard.
- The real-lamp, internet-unplugged check stays in Plan 7's exit gate, since it needs the Compose stack and a Zigbee coordinator.
