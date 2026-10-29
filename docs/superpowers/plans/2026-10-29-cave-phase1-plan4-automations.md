# CAVE Phase 1 · Plan 4: Config, automations and Test Center — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dashboards, automations and routines live as YAML files under `/config`, validated with line-numbered errors. Loading them makes them access-controlled items, and saving through the API refuses anything that controls what the saver can't. Automations run on triggers with run modes and step-by-step traces, notify people through the console bell, and can be rehearsed in the Test Center with zero side effects.

**Architecture:**
- **Config:** `cave/config/` loads YAML with a line map, validates it against Pydantic models that also export JSON Schemas, and turns each file into an item (`dashboard:<slug>`, `automation:<id>`, `sequence:<id>`) plus the entities it touches (`item_entities`). Files are the source of the *content*. The DB stays the source of *access*.
- **Engine:** `cave/automation/` has one interpreter for actions. It works against two small interfaces:
  - `StateReader`, which reads state
  - `Effects`, which does everything that changes the world: commands, notifications, MQTT publishes, scripts, sleeping

  A real run and a Test Center run use the same interpreter. Only the `Effects` and `StateReader` they pass differ, so "what if" can't drift from "what is".
- **Runtime:** an `AutomationManager` owns triggers, run modes and traces, and runs inside the app lifespan.

**Tech Stack:** Python 3.13, PyYAML (its `compose` gives node line numbers; no new dependency), Pydantic v2 (models and JSON Schema), the existing sandboxed Jinja in `cave/templates.py`, asyncio. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-25-cave-phase1-design.md`, sections "Where access settings live", "No back door through the editors", "What people see of devices they can't control", "Notifications in Phase 1", "Test Center", and the scope table rows "Dashboards" and "Automations". Background: the framework's sections "Dashboard YAML spec" and "Automation engine". This builds on Plans 1–3, all on `main`.

## Global Constraints

- Everything in Plans 1–3's Global Constraints still holds.
- File layout: `config/dashboards/<slug>.yaml`, `config/automations/<id>.yaml`, `config/sequences/<id>.yaml`. The file name is the ID: `^[a-z0-9_-]{1,64}$`.
- **Unknown keys fail validation, with the file name and line number.**
- Access settings never go in files. The framework's `visible_to` key is not in the dashboard schema.
- A new file becomes an item with the defaults (Restrict, others see it locked, no assignments). Loading **never changes an existing item's** Status, Visibility or assignments, only its name.
- A file whose content changed since the last load is written to the audit log as `config.file_changed`. Files can never widen access.
- **Save guard:** saving through the API runs `assert_can_save` over every entity the document **references**, meaning triggers, conditions, actions and template reads. It also needs `use` on every sequence it calls. Admins pass automatically.
- Template entity reads (`states('x')`, `is_state('x', …)`, `state_attr('x', …)`) must name the entity as a **string literal**, so the guard can see it.
- Run modes: `single` (default), `restart`, `queued`, `parallel`. `max` defaults to 10.
- Traces: the last **20** runs per automation or sequence are kept. Test Center runs are marked `test`, are kept separately (last 20 per automation), and never fire other automations.
- `notify` in Phase 1 has one target, `notify.cave`, the console bell. Recipients are the users named in `targets`, or else the user who last saved the automation, or else every Admin.
- What-if runs change **0 devices, send 0 messages, run 0 scripts**. This is asserted by test, by counting effects.
- Phase 1 trigger types, exactly: `state`, `numeric_state`, `time`, `time_pattern`, `startup`. Condition types: `state`, `numeric_state`, `time`, `template`, `and`, `or`, `not`. Action types: `call`, `notify`, `delay`, `wait_for`, `choose`, `repeat`, `sequence`, `script`, `set_variable`, `stop`, `mqtt_publish`.
- Deferred, each named in the docs as "coming later": the `sun`, `event`, `mqtt`, `webhook`, `device` and `zone` triggers; the `sun` condition; the `parallel` action; outgoing webhooks.
- Time triggers use the host's local time zone, with **minute** resolution.

## Review Focus

1. **A file edited by hand to reference a device its author couldn't control** → it loads, because files are trusted like the box itself, but it can't widen anyone's access. When the next non-Admin saves it through the API, the guard refuses with the device's name. Pinned in Task 4.
2. **A template that reads an entity through a variable** (`states(x)`, `states('cover.' ~ name)`) → refused when saved by a non-Admin, since the guard can't see what it reads. It still runs if an Admin saved it. Pinned in Task 3.
3. **A trigger firing again while a run is still going**, under each run mode → `single` drops it, `restart` cancels the old run, and `queued` and `parallel` respect `max`. Cancelled runs leave a trace that says so. Pinned in Task 6.
4. **A Test Center run of an automation that waits, delays, notifies, publishes and calls** → it finishes at once, with a "What if" line for each, and the real state machine, bus, notification table and MQTT publisher are untouched. Pinned in Task 8.
5. **A broken YAML file on disk at startup** → CAVE starts. The file is listed under `GET /api/v1/config/errors` with its line number, and its last good item keeps its access settings. Pinned in Task 4.

---

## File structure

```text
core/cave/config/__init__.py
core/cave/config/yamlfile.py          # load YAML with a line map; ConfigError with file:line
core/cave/config/models.py            # Pydantic models: Automation, Sequence, Dashboard (+ JSON Schema)
core/cave/config/refs.py              # entities and sequences a document references
core/cave/config/store.py             # load all files -> items + item_entities; save/delete; file-change audit
core/cave/templates.py                # + automation templates: states(), is_state(), state_attr(), now()
core/cave/automation/__init__.py
core/cave/automation/effects.py       # StateReader / Effects protocols, Trace
core/cave/automation/engine.py        # the interpreter: conditions + actions
core/cave/automation/manager.py       # triggers, run modes, persisted traces
core/cave/automation/whatif.py        # Test Center: overlay reader + recording effects
core/cave/notifications.py            # notify.cave storage + delivery
core/cave/api/config.py               # automations / sequences / dashboards CRUD, reload, errors, schemas
core/cave/api/automations.py          # manual run, traces, Test Center, notifications
core/cave/migrations/0004_automations.sql
core/cave/integrations/mqtt/config.py # switch to yamlfile line numbers (removes the Plan 3 shortcut)
schemas/automation.json  schemas/sequence.json  schemas/dashboard.json
core/tests/fixtures/config/...        # the UPS-on-battery example, adapted for Phase 1
docs/automations.md
```

---

### Task 1: YAML with line numbers

**Files:**
- Create: `core/cave/config/__init__.py`, `core/cave/config/yamlfile.py`
- Modify: `core/cave/integrations/mqtt/config.py` (use it; delete the `shortcut:` comment)
- Test: `core/tests/test_yamlfile.py`, `core/tests/test_mqtt_config.py` (tighten the expected messages)

**Interfaces:**
- Produces:
  - `class ConfigError(ValueError)` with `.file: str`, `.line: int | None`, `.path: str` and `.reason: str`. `str(e)` is exactly `f"{file}:{line}: {path}: {reason}"`, or `f"{file}: {path}: {reason}"` when there's no line.
  - `@dataclass(frozen=True) class YamlDoc: data: Any; lines: Mapping[tuple[str | int, ...], int]` — maps a key path to its 1-based line.
  - `load_text(text: str, file: str) -> YamlDoc`
  - `load_file(path: Path) -> YamlDoc`
  - `validate(model: type[M], doc: YamlDoc, file: str) -> M` — Pydantic validation. The first error is turned into a `ConfigError` with the deepest line known for its `loc`. An unknown-key error is preferred over a missing-key one, as Plan 3 does. Pydantic's discriminator segments (`'call'` and the like) are dropped from the path.
  - `path_text(loc) -> str` — Plan 3's `entities[0].colour` format, moved here.
- YAML safety: `yaml.compose` with `SafeLoader`. Documents over **256 KiB** are refused. Aliases and anchors are refused with `ConfigError("YAML anchors and aliases aren't supported")`, which also rules out billion-laughs expansion.
- `mqtt/config.py`'s `ConfigError` becomes this class (re-exported under the old name), so Plan 3's callers keep working.

- [ ] **Step 1: Write failing tests:**
  - `test_line_of_unknown_key` (line 7 for a typo on line 7)
  - `test_line_of_nested_list_item` (`actions[2].target`)
  - `test_missing_key_points_at_parent_line`
  - `test_yaml_syntax_error_has_line`
  - `test_aliases_refused`
  - `test_oversize_refused`
  - In `test_mqtt_config.py`, change the expected messages to include `:<line>:`.
- [ ] **Step 2:** Run `cd core && ../.venv/Scripts/python -m pytest -q tests/test_yamlfile.py tests/test_mqtt_config.py`. Expected: FAIL.
- [ ] **Step 3:** Implement. Walk the composed node tree once, recording `node.start_mark.line + 1` for every mapping key and sequence item.
- [ ] **Step 4:** Rerun, then the full suite with `-W error`, `ruff check .` and `mypy --strict cave`. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "feat(config): yaml loading with line-numbered errors"`

---

### Task 2: Models, references and JSON Schemas

**Files:**
- Create: `core/cave/config/models.py`, `core/cave/config/refs.py`, `schemas/automation.json`, `schemas/sequence.json`, `schemas/dashboard.json`
- Modify: `core/cave/__main__.py` (add a `schemas` subcommand)
- Test: `core/tests/test_config_models.py`, `core/tests/test_refs.py`, `core/tests/test_schemas.py`

**Interfaces:**
- Produces in `models.py`, all with `extra="forbid"`:
  - **Shared types.**
    - `Duration` accepts `"HH:MM:SS"`, `"MM:SS"` or a number of seconds, and normalises to `timedelta`. It is capped at 24 h for `delay`, `for` and `timeout`.
    - `EntityId` is a `str` matching the state machine's entity-ID pattern.
  - **Triggers**, discriminated on `type`:
    - `StateTrigger(entity, from_: str | None (alias "from"), to: str | None, for_: Duration | None (alias "for"))`
    - `NumericStateTrigger(entity, above: float | None, below: float | None, for_)`, where at least one of `above`/`below` is required
    - `TimeTrigger(at: "HH:MM")`
    - `TimePatternTrigger(minutes: int | "/N" | "*", hours: same)`
    - `StartupTrigger()`
  - **Conditions**, discriminated on `type`:
    - `StateCondition(entity, state: str | list[str])`
    - `NumericStateCondition(entity, above, below)`
    - `TimeCondition(after: "HH:MM" | None, before: "HH:MM" | None, weekdays: list["mon".."sun"] | None)`
    - `TemplateCondition(value: str)`
    - `And(conditions)`, `Or(conditions)`, `Not(conditions)`
  - **Actions**, discriminated on `type`:
    - `Call(target: EntityId, command: str, args: dict[str, Any] = {})`
    - `Notify(targets: list[str] = [], title: str | None, message: str)` — `targets` are `notify.cave` or `user:<username>`
    - `Delay(duration)`
    - `WaitFor(entity, to: str, timeout: Duration, on_timeout: "stop" | "continue" = "stop")`
    - `Choose(options: list[{conditions, actions}], default: list[Action] = [])`
    - `Repeat(count: int (1..1000) | None, while_: list[Condition] | None (alias "while"), until: list[Condition] | None, actions)` — exactly one of the three
    - `RunSequence(ref: "sequence.<id>", with_: dict (alias "with") = {})` (type name `sequence`)
    - `Script(ref: str, target: str | None, args: dict = {}, result_var: str | None)`
    - `SetVariable(name: identifier, value: Any)`
    - `Stop(reason: str | None)`
    - `MqttPublish(topic: str (no + or #), payload: str, retain: bool = False)`
  - `Automation(id, name, mode = "single", max: int (1..100) = 10, enabled: bool = True, triggers: list[Trigger] (min 1), conditions: list[Condition] = [], actions: list[Action] (min 1))`, wrapped in a top-level `automation:` key, as in the framework's examples.
  - `Sequence(id, name, fields: dict[identifier, {type: "int" | "float" | "str" | "bool", default?}] = {}, actions)`, wrapped in `sequence:`.
  - `Dashboard(title, icon: str | None, views: list[View])`, wrapped in `dashboard:`.
    - `View(id, title, sections: list[{title, cards: list[Card]}])`
    - `Card` is discriminated on `type`: `tile(entity, tap_action: "toggle" | "none" = "toggle")`, `entities(entities: list[EntityId])`, `gauge(entity, min, max, severity: dict | None)`, `button(name, action: "automation.<id>" | "sequence.<id>" | None, entity: EntityId | None, command: str | None, confirm: bool | None)` (an `action`, or an `entity`+`command` pair), and `markdown(content: str)`.
    - Every card has `w: int (1..12) = 3` and `h: int (1..8) = 1`.
  - The `id` inside an automation or sequence must equal the file name. Plan 4's store checks this.
  - Nesting cap: `choose`/`repeat`/`and`/`or`/`not` may nest at most **8** levels deep. This is checked after validation, as a `ConfigError` at the offending line.
- Produces in `refs.py`: `@dataclass(frozen=True) class Refs: entities: frozenset[str]; sequences: frozenset[str]; scripts: frozenset[str]; dynamic_template: bool`. `refs(doc: Automation | Sequence | Dashboard) -> Refs` walks every trigger, condition, action and card. It adds the entity IDs from `templates.entity_refs(...)` for every template string (Task 3), and sets `dynamic_template` when any template reads state through a non-literal.
- Produces: `python -m cave schemas [--out ../schemas]` writes the three `model_json_schema()` files, sorted, indented by 2 and ending with a newline.
- Templates appear in: `Notify.title`/`message`, `TemplateCondition.value`, `SetVariable.value` (when a string), `Call.args` string values, `MqttPublish.payload`, `RunSequence.with_` string values, `Script.args` string values, and `markdown.content`.

- [ ] **Step 1: Write failing tests:**
  - `test_framework_ups_example_validates`, using the framework's UPS automation adapted for Phase 1: `notify` targets are `notify.cave`, the `disk-report.sh` cave-host step is removed, and the sequence is the matching `lab_safe_shutdown`. Both fixtures go in `core/tests/fixtures/config/`.
  - `test_unknown_action_type_error_names_line`
  - `test_repeat_needs_exactly_one_mode`
  - `test_durations` (`"00:02:00"`, `"2:00"`, `120`; `"25:00:00"` refused)
  - `test_nesting_cap`
  - `test_dashboard_cards` (the framework's home dashboard minus `visible_to`, `media`, `camera` and `energy`)
  - `test_visible_to_is_unknown_key`
  - `test_refs_collects_everything` (the UPS automation → its entities and `sequence.lab_safe_shutdown`)
  - `test_refs_markdown_template`
  - `test_schemas_committed_match_generated` (regenerate in memory and compare with the files in `schemas/`)
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement, then run `python -m cave schemas` to write the committed files.
- [ ] **Step 4:** Rerun, then the full suite. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "feat(config): automation, sequence and dashboard schemas"`

---

### Task 3: Automation templates

**Files:**
- Modify: `core/cave/templates.py`
- Test: `core/tests/test_templates.py` (extend)

**Interfaces:**
- Produces:
  - `StateReader = Protocol` with `def get(self, entity_id: str) -> State | None`. It's defined here so templates and the engine share it, and `StateMachine` already satisfies it.
  - `render(template: str, variables: Mapping[str, Any], reader: StateReader, now: datetime) -> str` — the same allow-list and caps as `render_value`, plus four callables:
    - `states(entity_id) -> str` (the state value, or `"unknown"`)
    - `is_state(entity_id, value) -> bool`
    - `state_attr(entity_id, name) -> Any`
    - `now() -> datetime`
  - `entity_refs(template: str) -> tuple[frozenset[str], bool]` — the literal entity IDs read, and whether any read is non-literal.
- Allow-list change: `nodes.Call` is allowed **only** when it calls one of those four `Name`s. Everything Plan 3 refuses stays refused, and `render_value` (the MQTT device templates) still allows **no** calls at all.
- `render` returns the rendered string. Callers that need a number or bool parse it themselves. `TemplateCondition` is true when the result, stripped and lowercased, is in `{"true", "yes", "on", "1"}`.

- [ ] **Step 1: Write failing tests:**
  - `test_states_reads_reader`
  - `test_is_state_and_state_attr`
  - `test_unknown_entity_is_unknown`
  - `test_render_value_still_refuses_calls`
  - `test_other_calls_refused` (`range(3)`, `lipsum()`, `value.upper()`)
  - `test_entity_refs_literal` (`{{ states('sensor.a') }} {{ is_state('lock.b', 'locked') }}` → `{sensor.a, lock.b}`, not dynamic)
  - `test_entity_refs_dynamic` (Review Focus 2: `states(x)` and `states('cover.' ~ n)` → dynamic)
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement. A second environment shares `_Env` and the filter allow-list, and has the four callables as globals. `check()` takes `allowed_calls: frozenset[str]`.
- [ ] **Step 4:** Rerun, then the full suite. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "feat(templates): automation templates with state reads"`

---

### Task 4: The config store, the save guard and the API

**Files:**
- Create: `core/cave/config/store.py`, `core/cave/api/config.py`, `core/cave/migrations/0004_automations.sql`
- Modify: `core/cave/access/items.py` (add `ensure_item`), `core/cave/api/app.py` (load at startup; router)
- Test: `core/tests/test_config_store.py`, `core/tests/test_config_api.py`

**Interfaces:**
- Tables in `0004`:
  - `config_files(path TEXT PRIMARY KEY, sha256 TEXT NOT NULL, loaded_at TEXT NOT NULL)`
  - `config_saves(item_id TEXT PRIMARY KEY, user_id TEXT, saved_at TEXT)` — who last saved each file through the API, for notify's default recipient
  - `automation_traces(id INTEGER PRIMARY KEY, item_id TEXT, test INTEGER, started_at TEXT, finished_at TEXT, outcome TEXT, trace TEXT)` — used by Task 6
  - `notifications(id INTEGER PRIMARY KEY, user_id TEXT, title TEXT, message TEXT, source TEXT, created_at TEXT, read_at TEXT)` — used by Task 7
- Produces in `items.py`: `ensure_item(db, actor, item_id, kind, name) -> None`. It creates the item with defaults when missing. Otherwise it updates **only the name**, and audits that only if it changed. It never touches Status, Visibility, the network condition or assignments.
- Produces in `store.py`:
  - `Kind = Literal["automation", "sequence", "dashboard"]`
  - `item_id(kind, id) -> str` gives `"<kind>:<id>"`. Automations and sequences are `kind="action"` items; dashboards are `kind="dashboard"`.
  - `class ConfigStore(config_dir: Path, db, bus)`, with:
    - `load_all(actor: str = "system") -> None`. It reads every file under the three folders, validates each, and for each valid one:
      - calls `ensure_item`
      - calls `set_item_entities(…, refs.entities, bus=bus)` for dashboards (whose cards are what grant control), and for actions their **call, wait_for and template targets**
      - keeps the parsed model in memory

      A changed SHA-256 is audited as `config.file_changed` with old and new hashes. Invalid files go into `errors`, and their items stay as they were (Review Focus 5). Files that disappeared drop out of memory, but their items are kept, so access settings survive an accidental delete.
    - `errors: dict[str, str]` (relative path → `str(ConfigError)`)
    - `get(kind, id) -> tuple[model, text] | None`
    - `list(kind) -> list[model]`
    - `save(kind, id, text, p: Principal, ip, local_ranges, saved_by: str | None) -> model`:
      - validate (a `ConfigError` becomes a 422 upstream)
      - check that the inner `id` matches the file name
      - unless `p.is_admin`:
        - refuse `refs.dynamic_template` with `AccessDenied("Templates must name devices directly, like states('sensor.x').")`
        - run `assert_can_save(db, p, refs.entities, …)`
        - require `evaluate(..., use)` on each referenced sequence item
      - write atomically (temp file in the same folder, then `os.replace`)
      - audit `config.save` with the old and new **text**
      - record `config_saves`, then reload that one file

      The same rule also checks the **old** version: a non-Admin can't overwrite a file that references devices they can't control (Review Focus 1).
    - `delete(kind, id, p, ...) -> None`: the same guard on the existing file, then remove it, audit `config.delete`, and keep the item.
- Produces in `api/config.py`:
  - **Read:** `GET /api/v1/{kind}s` lists the items this caller has `listed`, each as `{id, name, allowed}`. `GET /api/v1/{kind}s/{id}` returns `{id, name, yaml}` and needs `use`, plus `can_control` on every referenced entity, so a file can't leak restricted devices' names.
  - **Write:** `PUT /api/v1/{kind}s/{id}` (body `{"yaml": str}`) and `DELETE /api/v1/{kind}s/{id}` need the section item: `section:automations` for automations and sequences, `section:dashboards` for dashboards. They return 422 `{"detail": "<file>:<line>: <path>: <reason>"}` for invalid YAML, and 403 with the `AccessDenied` message for the guard. Each publishes `access_changed`.
  - **Admin:** `POST /api/v1/config/reload` (Admin), `GET /api/v1/config/errors` (`section:system`), and `GET /api/v1/schemas/{name}.json` (any signed-in principal).
  - `{kind}` is spelled `automations`, `sequences` or `dashboards` in URLs.
- App startup: `create_app` builds `app.state.config = ConfigStore(settings.config_dir, db, bus)` and calls `load_all()` before the lifespan starts the manager (Task 6).

- [ ] **Step 1: Write failing tests:**
  - `test_load_creates_items_with_defaults_and_entities`
  - `test_reload_never_changes_access` (an Admin sets Show plus assignments; edit the file; reload → unchanged, and the audit holds `config.file_changed`)
  - `test_broken_file_listed_with_line_and_item_kept` (Review Focus 5)
  - `test_deleted_file_keeps_item`
  - `test_save_guard_blocks_operator` (the Operator saves an automation calling `cover.garage_door` → 403, naming it)
  - `test_operator_cannot_overwrite_file_with_foreign_device` (Review Focus 1)
  - `test_dynamic_template_refused_for_non_admin_allowed_for_admin` (Review Focus 2)
  - `test_sequence_use_required`
  - `test_save_writes_text_verbatim_with_comments`
  - `test_id_must_match_filename`
  - `test_get_yaml_needs_control_of_every_referenced_entity`
  - `test_invalid_yaml_422_with_line`
  - `test_dashboard_entities_grant_control` (put `cover.garage_door` on a dashboard assigned to sam → `can_control` becomes True after save)
  - `test_errors_and_reload_permissions`
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Rerun, then the full suite. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "feat(config): config store, save guard and config API"`

---

### Task 5: The engine

**Files:**
- Create: `core/cave/automation/__init__.py`, `core/cave/automation/effects.py`, `core/cave/automation/engine.py`
- Test: `core/tests/test_engine.py`

**Interfaces:**
- Produces in `effects.py`:
  - `class Effects(Protocol)`, with:
    - `async call(entity_id: str, command: str, args: dict[str, Any]) -> None`
    - `async notify(targets: list[str], title: str | None, message: str, source: str) -> None`
    - `async mqtt_publish(topic: str, payload: str, retain: bool) -> None`
    - `async run_script(ref: str, target: str | None, args: dict[str, Any]) -> dict[str, Any]`
    - `async sleep(seconds: float) -> None`
    - `async wait_for_state(entity_id: str, to: str, timeout: float) -> bool`
  - `@dataclass class Step: path: str; type: str; detail: str; started_at: datetime; result: Literal["ok", "skipped", "failed", "stopped", "what_if"]; data: dict[str, Any]`. `path` looks like `"actions[1]"` or `"actions[2].options[0].actions[1]"`.
  - `@dataclass class Trace: steps: list[Step]; outcome: Literal["finished", "stopped", "failed", "cancelled", "conditions_not_met"]; variables: dict[str, Any]; error: str | None`
- Produces in `engine.py`:
  - `class Engine(reader: StateReader, effects: Effects, sequences: Callable[[str], Sequence | None], now: Callable[[], datetime])`
  - `async run(actions: list[Action], variables: dict[str, Any], *, start_at: str | None = None, source: str) -> Trace`
    - It executes in order and records one `Step` per action. Template strings are rendered with `templates.render` and the current variables.
    - `call` renders string args.
    - `choose` runs the first option whose conditions all pass, else `default`.
    - `repeat` loops at most 1,000 times whatever its mode.
    - `sequence` resolves the sequence, applies `fields` defaults, checks types (a bad `with` value fails the step), and runs its actions in a child scope. The child's `set_variable` doesn't leak out.
    - `script` stores the returned dict in `variables[result_var]`.
    - `stop` ends with outcome `stopped`.
    - An exception in a step records it as `failed` and ends the trace with that outcome and error. Templates that fail count as step failures too.
    - `start_at` skips every step before that path. Skipped steps are recorded as `skipped`. Nested paths are supported.
    - Sequence call depth is capped at 8, which catches a routine that calls itself.
  - `async check(conditions: list[Condition], variables) -> tuple[bool, list[Step]]` — `time` uses `now()` in local time. Each condition's result is recorded.
- The engine never touches the state machine, the bus or the DB directly. Only `reader` and `effects` do.

- [ ] **Step 1: Write failing tests**, with a `FakeEffects` that records calls, a dict-backed reader and a fixed clock:
  - `test_actions_run_in_order_with_trace`
  - `test_templates_render_with_variables_and_states`
  - `test_choose_and_default`
  - `test_repeat_count_while_until_and_cap`
  - `test_wait_for_timeout_stop_and_continue`
  - `test_sequence_fields_defaults_and_scope`
  - `test_sequence_recursion_capped`
  - `test_script_result_var`
  - `test_stop_and_failure_outcomes`
  - `test_start_at_skips_earlier_steps_nested`
  - `test_conditions_all_types` (including `time` with weekdays across midnight: `after: "22:00", before: "06:00"`)
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Rerun, then the full suite. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "feat(automation): action interpreter with traces"`

---

### Task 6: Triggers, run modes and the manager

**Files:**
- Create: `core/cave/automation/manager.py`
- Modify: `core/cave/api/app.py` (lifespan starts and stops the manager; reload re-arms triggers)
- Test: `core/tests/test_manager.py`

**Interfaces:**
- Produces: `class AutomationManager(store: ConfigStore, db, states: StateMachine, bus: EventBus, effects: Effects, now: Callable[[], datetime] = …)`, with:
  - `async start()` — subscribes to the bus. It fires `startup` triggers once, and starts a minute ticker for `time` and `time_pattern`. The ticker sleeps to the next minute boundary, so it can't drift.
  - `async stop()` — cancels the ticker, pending `for:` timers and running runs.
  - `rearm()` — called after `ConfigStore` saves or reloads. It rebuilds the trigger index from enabled automations and drops pending `for:` timers whose automation changed.
  - `async trigger(automation_id: str, trigger_data: dict, source: str) -> int | None` — the trace ID, or `None` when the run mode dropped it.
  - `traces(item_id: str, test: bool = False, limit: int = 20) -> list[dict]`
- Trigger semantics:
  - `state` fires on a `state_changed` whose `old`/`new` match `from`/`to` (both optional), ignoring changes where only attributes changed.
  - `numeric_state` fires when the value crosses into the range, not on every update while it's inside.
  - `for:` starts a timer when the condition becomes true and cancels it if the condition stops holding first.
  - `time` fires at `HH:MM` local.
  - `time_pattern` takes `minutes: "/15"` style patterns.
  - Each fire runs `engine.check(conditions)`. A failure records a trace with outcome `conditions_not_met`.
  - Variables available to templates: `trigger` (`{type, entity, from, to, at}`).
- Run modes, per automation:
  - `single` drops a new trigger while one runs, logs it, and records no trace.
  - `restart` cancels the running task. Its trace ends `cancelled`.
  - `queued` runs triggers one after another, keeping at most `max` waiting and dropping beyond that.
  - `parallel` runs at most `max` at once and drops beyond that.
- Traces: each run is persisted to `automation_traces` when it ends. Rows beyond the newest 20 per `(item_id, test)` are deleted.
- Enabled flag: `enabled: false` automations are never armed. The item's Status (`disabled`) also disarms it.

- [ ] **Step 1: Write failing tests**, using a manual clock and `asyncio.run` around the manager, with `FakeEffects`:
  - `test_state_trigger_from_to`
  - `test_attribute_only_change_ignored`
  - `test_numeric_state_crossing_only`
  - `test_for_duration_fires_and_cancels`
  - `test_time_and_time_pattern` (advance the fake clock)
  - `test_startup_trigger`
  - `test_conditions_not_met_trace`
  - `test_run_modes` (Review Focus 3: one parametrized test per mode, using an action that waits on an `asyncio.Event` the test controls)
  - `test_traces_capped_at_20`
  - `test_disabled_automation_and_disabled_item_not_armed`
  - `test_rearm_after_save`
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Rerun three times for flakiness, then the full suite. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "feat(automation): triggers, run modes and traces"`

---

### Task 7: Real effects and `notify.cave`

**Files:**
- Create: `core/cave/notifications.py`
- Modify: `core/cave/automation/effects.py` (`LiveEffects`), `core/cave/api/ws.py` (deliver `notification` events), `core/cave/api/app.py`
- Test: `core/tests/test_notifications.py`, `core/tests/test_live_effects.py`

**Interfaces:**
- Produces in `notifications.py`:
  - `recipients(db, targets: list[str], item_id: str) -> list[str]` (user IDs) — `user:<username>` names a user; `notify.cave` alone means the last saver from `config_saves`, falling back to every enabled Admin. Disabled users are skipped.
  - `create(db, bus, user_ids, title, message, source) -> None` — inserts one row each and publishes `{"type": "notification", "user_id", "id", "title", "message"}`.
  - `list_for(db, user_id, unread_only: bool) -> list[dict]`
  - `mark_read(db, user_id, ids: list[int]) -> None`
- Produces in `effects.py`: `class LiveEffects(states, db, bus, mqtt_getter: Callable[[], MqttBridge | None])`:
  - `call` goes through `states.command`. Automations act as the system, and the save guard is what checked the author.
  - `notify` goes through `notifications`.
  - `mqtt_publish` goes through the bridge, raising `ValueError("MQTT isn't set up.")` when there's none.
  - `run_script` raises `ValueError("Scripts arrive with the script runner (Phase 1 plan 5).")`.
  - `sleep` is `asyncio.sleep`.
  - `wait_for_state` subscribes to the bus and returns when the entity reaches `to`, or `False` at the timeout.
- Produces in the API (`api/automations.py`, started here):
  - `GET /api/v1/notifications?unread=true`
  - `POST /api/v1/notifications/read {ids}`
  - The WS delivers `notification` events only to the matching user's sockets (not to screens).
- Message length is capped at 2,000 characters and titles at 120, and both are truncated with `…`.

- [ ] **Step 1: Write failing tests:**
  - `test_recipients_default_to_last_saver_then_admins`
  - `test_disabled_user_skipped`
  - `test_notification_api_and_mark_read`
  - `test_ws_delivers_only_to_recipient`
  - `test_live_call_goes_through_state_machine`
  - `test_wait_for_state_true_and_timeout`
  - `test_script_not_available_yet`
  - `test_message_truncated`
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Rerun, then the full suite. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "feat(automation): live effects and console notifications"`

---

### Task 8: The Test Center

**Files:**
- Create: `core/cave/automation/whatif.py`
- Modify: `core/cave/api/automations.py`
- Test: `core/tests/test_whatif.py`

**Interfaces:**
- Produces in `whatif.py`:
  - `class OverlayReader(base: StateReader, overrides: Mapping[str, tuple[str, dict[str, Any]]])` — returns the simulated state for overridden entities, and the real one otherwise.
  - `class WhatIfEffects(script_samples: Mapping[str, dict[str, Any]])` records every effect as a `Step` with `result="what_if"` and a `detail` that starts `"What if: "`:
    - `call` → `What if: turn_off switch.proxmox_vm_media`
    - `notify` → its rendered title and message
    - `mqtt_publish` → the topic and payload
    - `run_script` returns the sample for that ref (from `script_samples`, or `{}`) and records `"not run"`
    - `sleep` returns at once and records the duration
    - `wait_for_state` returns `True` at once, unless the overlay says otherwise. With an override present it checks that value. Without one it assumes the wait is met and says so.

    It also counts `devices_changed`, `messages_sent` and `scripts_run`, which stay at **0** by construction. A summary line is added to the trace.
  - `async what_if(doc: Automation | Sequence, *, trigger: dict | None, states: dict[str, str | dict], variables: dict, start_at: str | None, script_samples: dict, reader: StateReader, sequences, now) -> Trace` — for an automation it checks conditions first, against the overlay.
- Produces in the API: `POST /api/v1/test-center/run`. The body is `{kind: "automation" | "sequence", id: str | null, yaml: str | null, trigger: {...} | null, states: {...}, variables: {...}, start_at: str | null, script_samples: {...}}`.
  - Either `id` (the saved version) or `yaml` (a draft) must be given. A draft goes through `validate` (422 on error) but is **never written**.
  - It needs `use` on `feature:test_center`, plus the same reference rule as saving. A trace shows real state for entities without an override, so testing can't reveal devices the tester can't control.
  - It returns `{trace, summary: {devices_changed: 0, messages_sent: 0, scripts_run: 0}}`.
  - It stores the trace with `test=1` against the item when `id` is given.

- [ ] **Step 1: Write failing tests:**
  - `test_ups_example_whole_run` (the spec's exit-gate example: UPS on battery for 2 min, runtime 12 → a "What if" line per action, with `lab.status` from the script sample and the rendered notify text)
  - `test_ups_example_step_two_only` (`start_at: "actions[1]"`, with `variables`)
  - `test_conditions_fail_reported` (runtime 30 → `conditions_not_met`)
  - `test_zero_side_effects` (Review Focus 4: snapshot the state machine values, bus subscriber queue, notification rows and the MQTT `FakePublisher` before and after → identical; summary all zeros)
  - `test_draft_not_written`
  - `test_feature_and_reference_guard` (household → 403; operator without control of the referenced lock → 403)
  - `test_test_traces_stored_separately`
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Rerun, then the full suite. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "feat(test-center): what-if runs with zero side effects"`

---

### Task 9: Manual runs, traces API and docs

**Files:**
- Modify: `core/cave/api/automations.py`, `README.md` (one link)
- Create: `docs/automations.md`
- Test: `core/tests/test_automation_api.py`

**Interfaces:**
- `POST /api/v1/automations/{id}/run` and `POST /api/v1/sequences/{id}/run` (body `{variables?: {}}`) need `use` on that action item, so this is how a household member's "Run" button works. They skip triggers and conditions for automations, run the actions, and return `{"trace_id"}`. If the run mode drops it, they return 409 `{"detail": "It's already running."}`.
- `GET /api/v1/automations/{id}/traces?test=false` and the same for sequences need `section:run_history` or `section:automations`. Each trace's `data` is filtered through `can_control` for the caller, so entity values the caller can't control appear as `"restricted"`.
- `docs/automations.md` covers:
  - file locations
  - the YAML for each trigger, condition and action, with one example each
  - run modes
  - templates (the allow-list and the literal-device rule)
  - the save guard, in plain words
  - the Test Center
  - "coming later" for the deferred trigger types
  - pointers to the `schemas/` files for editor autocompletion

- [ ] **Step 1: Write failing tests:**
  - `test_household_runs_assigned_action`
  - `test_run_refused_without_assignment`
  - `test_single_mode_409`
  - `test_traces_permission_and_redaction`
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement, and write the docs.
- [ ] **Step 4:** Rerun, then the full suite. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "feat(automation): manual runs, traces api and docs"`

---

## Plan 4 done when

- CI is green: ruff, mypy --strict, pytest.
- The spec's exit-gate item 3 passes as a test: the adapted UPS-on-battery automation runs in the Test Center against simulated inputs, both whole and from step 2, with a summary of 0 devices changed, 0 messages sent and 0 scripts run.
- The editor back door is closed: a non-Admin can't save, overwrite, delete, read or test anything that references a device they can't control, or that reads devices through a non-literal template.
- A broken file never stops CAVE, and loading files never changes access.
- Left for later plans: the sentence builder and recipes (the console, Plan 6), and the script runner behind the `script` action (Plan 5, which replaces `LiveEffects.run_script`).
