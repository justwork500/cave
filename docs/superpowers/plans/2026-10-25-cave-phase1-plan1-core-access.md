# CAVE Phase 1 · Plan 1: Core and access model — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A public-ready repo with a Python core that signs people in, holds entities and live state, and enforces the CAVE access model on every read, command and save over REST and WebSocket.

**Architecture:** One Python package `cave` under `core/`. FastAPI serves REST and one WebSocket; SQLite (WAL) holds users, groups, items, assignments, sessions, tokens and the audit log; live state is in memory with an async event bus. A single function, `cave.access.evaluate`, decides every request, and everything else calls it.

**Tech Stack:** Python 3.13, FastAPI, uvicorn, Pydantic v2, stdlib `sqlite3`, argon2-cffi, pyotp, PyYAML; pytest, httpx (FastAPI `TestClient`), ruff, mypy --strict; GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-25-cave-phase1-design.md` (background: `docs/CAVE-Design-Framework.md`)

## Phase 1 plan sequence

Phase 1 is seven plans, run in order. Each one ends in working, tested software. Only Plan 1 is written in detail here; each later plan is written once the one before it has merged, from the spec and the code that exists by then.

| # | Plan | Delivers | Depends on |
| --- | --- | --- | --- |
| 1 | **Core and access model** (this document) | Repo, DB, sign-in with TOTP, registry and state, access evaluation, command and save guards, filtered reads, access admin API, API tokens, audit log | — |
| 2 | Screens, networks and HTTPS | Screen enrollment with WebCrypto non-extractable keys, challenge sign-in, Admin approval, self-signed cert on first run, Networks and trusted proxies admin API; **starts with the browser spike** from the spec | 1 |
| 3 | MQTT | Mosquitto sidecar, MQTT discovery mapping to `light`, `switch`, `sensor`, `binary_sensor`, `cover`, `lock`, `button`; manual MQTT entities in YAML; `mqtt.publish` | 1 |
| 4 | Config, automations and Test Center | YAML loader with JSON Schemas for dashboards, automations, sequences; engine (triggers, conditions, actions, run modes, traces); `notify.cave`; what-if executor with zero side effects | 1, 3 |
| 5 | Scripts | `cave-script-runner` image (pwsh 7, python3, bash), header parser incl. `sample:`, run contract, sandbox limits, script action step | 4 |
| 6 | Console and dashboards | React + Fluent UI console sections from the spec, Actions dashboard, card types `tile`, `entities`, `gauge`, `button`, `markdown`, locked tiles, sentence builder and recipes | 1–5 |
| 7 | Install and exit gate | `compose.yaml` (profiles `mqtt`, `scripts`), Debian 13 install guide, the spec's four exit-gate checks automated end to end | 1–6 |

Plans 2 and 3 can run in parallel once Plan 1 is merged.

## Global Constraints

- Local-first: no code path may need the internet. No telemetry.
- Python 3.13; `mypy --strict` and `ruff` clean on `core/`.
- License Apache-2.0; contributions use DCO sign-off (`git commit -s`), no CLA.
- No Home Assistant code, branding or trade dress.
- Passwords hashed with Argon2id (`argon2-cffi`). TOTP via `pyotp`, required for Admins and Operators.
- Lockout: 5 failed attempts → locked 15 minutes. Every attempt logged.
- Session cookie: `Secure`, `HttpOnly`, `SameSite=Strict`, 12-hour idle timeout.
- 10 one-time recovery codes when MFA is set up.
- The server decides every request; hiding in the UI is cosmetic.
- New items default to Visibility `restrict`, `others_see` `locked`, no assignments. Built-in sections and features default to `restrict`, `others_see` `none`, with the spec's starting role assignments.
- Access settings live in the database, never in `/config` files.
- Every access or user change is written to the audit log with actor, action, target, old value and new value.
- The last enabled Admin can't be disabled, demoted, or removed.
- Roles, exactly: `admin`, `operator`, `household`, `guest`, `auditor`.
- API under `/api/v1`. Restricted entity stub, exactly: `{"entity_id", "name", "area_id", "restricted": true}`.
- Tests never touch real devices or the network.

## Review Focus

1. **Spoofed `X-Forwarded-For` from an untrusted peer** → ignored; the socket address is used. Pinned in Task 6.
2. **IPv4-mapped IPv6 client addresses** (`::ffff:192.168.1.5`) → matched against IPv4 local ranges as the IPv4 address. Pinned in Task 6.
3. **A user disabled while their WebSocket is open** → the socket closes at once and no further events arrive. Pinned in Task 9.
4. **An entity removed from the only item that gave someone access, while they're subscribed** → that entity's `state_changed` events stop, and the next read returns the stub. Pinned in Task 9.
5. **Unknown username at login** → same error text and timing class as a wrong password, and the attempt is logged. No user enumeration. Pinned in Task 3.

---

## File structure

```text
LICENSE  README.md  CONTRIBUTING.md  CODE_OF_CONDUCT.md  SECURITY.md  CLAUDE.md  .gitignore
.github/workflows/core.yml
core/pyproject.toml
core/cave/__init__.py
core/cave/settings.py          # Settings dataclass
core/cave/db.py                # Database: connection, lock, migrations
core/cave/schema.sql           # all tables, applied via PRAGMA user_version
core/cave/audit.py             # record / list audit entries
core/cave/auth/passwords.py    # Argon2id hash/verify
core/cave/auth/users.py        # user CRUD, lockout, TOTP, recovery codes
core/cave/auth/sessions.py     # session create/lookup/touch/end
core/cave/auth/tokens.py       # API tokens
core/cave/state.py             # EventBus, StateMachine, entity registry
core/cave/access/model.py      # Principal, Item, Decision, enums
core/cave/access/network.py    # resolve_client_ip, is_local
core/cave/access/evaluate.py   # evaluate(), can_control(), assert_can_save()
core/cave/access/items.py      # item + assignment + item_entities storage, seeding
core/cave/api/app.py           # create_app()
core/cave/api/deps.py          # current principal, client ip
core/cave/api/auth.py          # /auth/*, /me
core/cave/api/entities.py      # /states, /entities, commands
core/cave/api/admin.py         # users, groups, items, assignments, tokens, audit
core/cave/api/ws.py            # /ws
core/tests/...                 # one test module per source module
```

---

### Task 1: Repository foundation

**Files:**
- Create: `LICENSE` (Apache-2.0 full text), `README.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1), `SECURITY.md`, `CLAUDE.md`, `.gitignore`, `.github/workflows/core.yml`, `core/pyproject.toml`, `core/cave/__init__.py`, `core/cave/settings.py`, `core/cave/api/app.py`
- Test: `core/tests/test_health.py`

**Interfaces:**
- Produces: `Settings(db_path: Path, config_dir: Path, session_idle_hours: int = 12, local_ranges: list[str] = [], trusted_proxies: list[str] = [])` (frozen dataclass); `create_app(settings: Settings) -> FastAPI`; `GET /api/v1/health` → `{"status": "ok"}`.

- [ ] **Step 1:** `git init` in the repo root, then create `.gitignore` with Python/node defaults plus `.superpowers/`, `data/`, `.venv/`.
- [ ] **Step 2: Write the failing test**

```python
def test_health(tmp_path):
    app = create_app(Settings(db_path=tmp_path / "cave.db", config_dir=tmp_path))
    r = TestClient(app).get("/api/v1/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}
```

- [ ] **Step 3:** Run `cd core && python -m pytest tests/test_health.py -v`. Expected: FAIL (import error).
- [ ] **Step 4:** Write `core/pyproject.toml` (project `cave`, `requires-python = ">=3.13"`, deps `fastapi`, `uvicorn[standard]`, `pydantic>=2`, `argon2-cffi`, `pyotp`, `pyyaml`; extra `dev` = `pytest`, `httpx`, `ruff`, `mypy`), `Settings`, and `create_app` with the health route.
- [ ] **Step 5:** `pip install -e "core[dev]"`, then rerun. Expected: PASS. Also `ruff check core` and `mypy --strict core/cave` are clean.
- [ ] **Step 6:** Write the docs. README: what CAVE is (spec "Intent"), local-first promise, status "Phase 1 in progress", link to the spec. CONTRIBUTING: DCO sign-off, the lint/test commands, "architecture changes need an ADR in `docs/adr/`". SECURITY.md: report privately via GitHub security advisories. CLAUDE.md: test commands, "never call real devices in tests", "never log secrets", "every access check goes through `cave.access.evaluate`".
- [ ] **Step 7:** Write `.github/workflows/core.yml`: on push and PR, Python 3.13, install `core[dev]`, run ruff, mypy --strict, pytest.
- [ ] **Step 8: Commit** `git commit -s -m "chore: repository foundation and health endpoint"`

---

### Task 2: Database and audit log

**Files:**
- Create: `core/cave/db.py`, `core/cave/schema.sql`, `core/cave/audit.py`
- Test: `core/tests/test_db.py`, `core/tests/test_audit.py`

**Interfaces:**
- Produces: `class Database` with `Database.open(path: Path) -> Database`, `execute(sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor`, `transaction() -> ContextManager[sqlite3.Connection]`. One `sqlite3` connection, `check_same_thread=False`, guarded by a `threading.Lock`; `PRAGMA journal_mode=WAL`, `foreign_keys=ON`; rows as `sqlite3.Row`.
- Produces: `audit.record(db: Database, actor: str, action: str, target: str, old: Any = None, new: Any = None) -> None` (old/new stored as JSON); `audit.list_entries(db: Database, limit: int = 100) -> list[dict[str, Any]]`, newest first, each with `time, actor, action, target, old, new`.
- Tables in `schema.sql` (version 1): `users(id, username UNIQUE, display_name, role, enabled, expires_at, password_hash, totp_secret, created_at)`, `recovery_codes(user_id, code_hash, used_at)`, `login_attempts(username, at, ok, ip)`, `sessions(id, user_id, created_at, last_seen)`, `groups(id, name UNIQUE)`, `group_members(group_id, user_id)`, `items(id, kind, name, status, visibility, others_see, network, builtin)`, `assignments(item_id, target_kind, target_id)`, `item_entities(item_id, entity_id)`, `api_tokens(id, user_id, name, token_hash, created_at, revoked_at)`, `audit(id, time, actor, action, target, old, new)`. Exact column types are the builder's call.

- [ ] **Step 1: Write failing tests**

```python
def test_open_is_idempotent_and_wal(tmp_path):
    Database.open(tmp_path / "c.db"); db = Database.open(tmp_path / "c.db")
    assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert db.execute("PRAGMA user_version").fetchone()[0] == 1

def test_audit_records_old_and_new(db):
    audit.record(db, "user:1", "item.update", "item:home", {"visibility": "show"}, {"visibility": "restrict"})
    e = audit.list_entries(db)[0]
    assert (e["actor"], e["action"], e["target"]) == ("user:1", "item.update", "item:home")
    assert e["old"] == {"visibility": "show"} and e["new"] == {"visibility": "restrict"}
```

Put a `db` fixture in `core/tests/conftest.py` returning `Database.open(tmp_path / "t.db")`, and a module constant `T0 = datetime(2026, 1, 1, tzinfo=UTC)` that later tests import.

- [ ] **Step 2:** Run `pytest tests/test_db.py tests/test_audit.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `Database` and `audit`. Migrations apply `schema.sql` when `user_version < 1`, then set it to 1.
- [ ] **Step 4:** Rerun. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "feat(core): sqlite database and audit log"`

---

### Task 3: Users, passwords, lockout, TOTP, recovery codes

**Files:**
- Create: `core/cave/auth/passwords.py`, `core/cave/auth/users.py`
- Test: `core/tests/test_users.py`

**Interfaces:**
- Consumes: `Database`, `audit.record`.
- Produces:
  - `Role = Literal["admin", "operator", "household", "guest", "auditor"]`
  - `@dataclass(frozen=True) class User: id: str; username: str; display_name: str; role: Role; enabled: bool; expires_at: datetime | None; has_totp: bool`
  - `create_user(db, actor: str, username: str, password: str, role: Role, display_name: str = "") -> User`
  - `get_user(db, user_id: str) -> User | None`
  - `class LoginError(Exception)` with `.message: str`
  - `check_password(db, username: str, password: str, ip: str, now: datetime) -> User` — raises `LoginError("Wrong username or password.")` for unknown user or bad password, `LoginError("Too many attempts. Try again in 15 minutes.")` when locked. Logs every attempt to `login_attempts`.
  - `mfa_required(user: User) -> bool` — True for `admin`, `operator`, or anyone with TOTP set up.
  - `setup_totp(db, user_id: str) -> tuple[str, list[str]]` — returns provisioning URI and 10 recovery codes (stored hashed).
  - `verify_second_factor(db, user_id: str, code: str) -> bool` — accepts a current TOTP code, or an unused recovery code (then marks it used).

- [ ] **Step 1: Write failing tests**

```python
def test_lockout_after_five_failures(db):
    create_user(db, "system", "sam", "correct horse", "household")
    for _ in range(5):
        with pytest.raises(LoginError): check_password(db, "sam", "nope", "1.1.1.1", T0)
    with pytest.raises(LoginError, match="Too many attempts"):
        check_password(db, "sam", "correct horse", "1.1.1.1", T0 + timedelta(minutes=14))
    assert check_password(db, "sam", "correct horse", "1.1.1.1", T0 + timedelta(minutes=16)).username == "sam"

def test_unknown_user_same_message_and_logged(db):          # Review Focus 5
    with pytest.raises(LoginError) as e: check_password(db, "ghost", "x", "1.1.1.1", T0)
    assert e.value.message == "Wrong username or password."
    assert db.execute("SELECT count(*) FROM login_attempts WHERE username='ghost'").fetchone()[0] == 1

def test_admin_and_operator_need_mfa(db):
    assert mfa_required(create_user(db, "system", "a", "pw-aaaaaaaa", "admin"))
    assert mfa_required(create_user(db, "system", "o", "pw-aaaaaaaa", "operator"))
    assert not mfa_required(create_user(db, "system", "h", "pw-aaaaaaaa", "household"))

def test_recovery_code_is_single_use(db):
    u = create_user(db, "system", "a", "pw-aaaaaaaa", "admin")
    _, codes = setup_totp(db, u.id)
    assert len(codes) == 10
    assert verify_second_factor(db, u.id, codes[0]) and not verify_second_factor(db, u.id, codes[0])

def test_password_is_argon2id(db):
    u = create_user(db, "system", "a", "pw-aaaaaaaa", "admin")
    h = db.execute("SELECT password_hash FROM users WHERE id=?", (u.id,)).fetchone()[0]
    assert h.startswith("$argon2id$")
```

For the unknown-user case, still run one Argon2 verify against a fixed dummy hash, so the timing matches a wrong password.

- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement. IDs are `uuid4().hex`. Lockout counts failures for that username in the last 15 minutes since the last success. `create_user` writes an audit entry `user.create` (no password in old/new).
- [ ] **Step 4:** Rerun. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "feat(auth): users, argon2id, lockout, totp and recovery codes"`

---

### Task 4: Sessions and sign-in API

**Files:**
- Create: `core/cave/auth/sessions.py`, `core/cave/api/deps.py`, `core/cave/api/auth.py`
- Modify: `core/cave/api/app.py` (store `Database` on `app.state.db`, include routers)
- Test: `core/tests/test_api_auth.py`

**Interfaces:**
- Produces:
  - `sessions.create(db, user_id: str, now: datetime) -> str` (32-byte `secrets.token_urlsafe`); `sessions.lookup(db, session_id: str, now: datetime, idle: timedelta) -> str | None` (returns user_id and touches `last_seen`; `None` if idle-expired); `sessions.end_for_user(db, user_id: str) -> None`.
  - `POST /api/v1/auth/login {username, password}` → `200 {"mfa_required": bool}`. If MFA is needed, it sets a short-lived `cave_pending` cookie instead of a session.
  - `POST /api/v1/auth/mfa {code}` → `200`, with the `cave_session` cookie set.
  - `POST /api/v1/auth/logout` → `204`.
  - `GET /api/v1/me` → `{"id", "username", "display_name", "role"}`.
  - `deps.current_user(request) -> User` raising 401.
  - Errors use `{"detail": "<message>"}`, with the `LoginError.message` text.

- [ ] **Step 1: Write failing tests**

```python
def test_household_login_sets_strict_cookie(client, users):
    r = client.post("/api/v1/auth/login", json={"username": "sam", "password": "pw-sam-1234"})
    assert r.json() == {"mfa_required": False}
    c = r.headers["set-cookie"].lower()
    assert "cave_session=" in c and "httponly" in c and "secure" in c and "samesite=strict" in c

def test_admin_needs_second_factor_before_session(client, users):
    r = client.post("/api/v1/auth/login", json={"username": "admin", "password": "pw-admin-1234"})
    assert r.json() == {"mfa_required": True}
    assert client.get("/api/v1/me").status_code == 401
    client.post("/api/v1/auth/mfa", json={"code": users.admin_totp.now()})
    assert client.get("/api/v1/me").json()["role"] == "admin"

def test_session_idle_timeout(db):
    sid = sessions.create(db, "u1", T0)
    assert sessions.lookup(db, sid, T0 + timedelta(hours=11), timedelta(hours=12)) == "u1"
    assert sessions.lookup(db, sid, T0 + timedelta(hours=23, minutes=1), timedelta(hours=12)) is None
```

The `client` fixture builds the app with `TestClient(app, base_url="https://testserver")`, so Secure cookies round-trip. The `users` fixture creates `admin` (with TOTP; it exposes `admin_totp: pyotp.TOTP`), `sam` (household), `op` (operator), `aud` (auditor).

- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement. The pending-MFA cookie lasts 5 minutes and is bound to a user_id.
- [ ] **Step 4:** Rerun. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "feat(api): sign-in, mfa step and sessions"`

---

### Task 5: Entity registry, state machine, event bus

**Files:**
- Create: `core/cave/state.py`
- Modify: `core/cave/api/app.py` (`app.state.states`, `app.state.bus`)
- Test: `core/tests/test_state.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Entity: entity_id: str; name: str; area_id: str | None; capability: str` (the capability is the prefix before `.`).
  - `@dataclass(frozen=True) class State: entity_id: str; value: str; attributes: Mapping[str, Any]; last_changed: datetime; last_updated: datetime`
  - `class EventBus`: `subscribe() -> asyncio.Queue[Event]`, `unsubscribe(q) -> None`, `publish(event: Event) -> None` (non-blocking, fan-out); `Event = dict[str, Any]` with key `type`.
  - `class StateMachine(bus: EventBus)`: `register(entity: Entity) -> None`, `remove(entity_id: str) -> None`, `entities() -> list[Entity]`, `get(entity_id) -> State | None`, `set(entity_id: str, value: str, attributes: Mapping[str, Any] | None = None) -> State`, which publishes `{"type": "state_changed", "entity_id", "old", "new", "attributes"}`; `last_changed` moves only when `value` changes.
  - `CommandHandler = Callable[[str, str, dict[str, Any]], Awaitable[None]]`; `StateMachine.set_command_handler(capability: str, handler: CommandHandler)`; `async StateMachine.command(entity_id, command, args) -> None` raises `KeyError` with no handler. (MQTT registers handlers in Plan 3.)

- [ ] **Step 1: Write failing tests:** `test_set_publishes_state_changed` (subscribe, `set("light.kitchen", "on")`, the queue gets an event with `old is None`, `new == "on"`); `test_last_changed_only_moves_on_value_change` (same value with new attributes keeps `last_changed`); `test_entity_id_must_have_known_capability` (`register(Entity("garage", ...))` raises `ValueError`; valid prefixes are the spec's Phase 1 capability list from the framework).
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement. In-memory only. Entities persist with Plan 4's config loader.
- [ ] **Step 4:** Rerun. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "feat(core): entity registry, state machine, event bus"`

---

### Task 6: Access model and evaluation

The heart of Phase 1. Every later check calls these functions.

**Files:**
- Create: `core/cave/access/model.py`, `core/cave/access/network.py`, `core/cave/access/items.py`, `core/cave/access/evaluate.py`
- Test: `core/tests/test_network.py`, `core/tests/test_evaluate.py`

**Interfaces:**
- Produces in `model.py`:
  - `ItemKind = Literal["dashboard", "section", "action", "feature"]`; `Status = Literal["enabled", "disabled"]`; `Visibility = Literal["show", "hide", "restrict"]`; `OthersSee = Literal["locked", "none"]`; `NetworkCond = Literal["anywhere", "local"]`; `TargetKind = Literal["user", "group", "role", "screen"]`.
  - `@dataclass(frozen=True) class Item: id: str; kind: ItemKind; name: str; status: Status = "enabled"; visibility: Visibility = "restrict"; others_see: OthersSee = "locked"; network: NetworkCond = "anywhere"; builtin: bool = False`
  - `@dataclass(frozen=True) class Principal: kind: Literal["user", "screen", "token"]; id: str; user_id: str | None; role: Role | None; group_ids: frozenset[str]; active: bool`, plus `is_admin` (property: `role == "admin" and kind != "screen"`). For a token, the fields are the owner's, with `kind="token"`.
  - `@dataclass(frozen=True) class Decision: allowed: bool; listed: bool` (`listed` = show it in lists, locked if not allowed).
- Produces in `network.py`:
  - `IPAddress = IPv4Address | IPv6Address` (used as the `client_ip` type everywhere)
  - `resolve_client_ip(peer: str, forwarded_for: str | None, trusted: Sequence[str]) -> IPv4Address | IPv6Address` — if `peer` isn't in a trusted CIDR, return `peer`. Otherwise walk `X-Forwarded-For` right to left, skipping trusted addresses, and return the first untrusted one (or `peer` if none). IPv4-mapped IPv6 is normalized to IPv4.
  - `is_local(ip, local_ranges: Sequence[str]) -> bool`
- Produces in `items.py`: `upsert_item(db, actor: str, item: Item) -> None` (audited `item.create` / `item.update` with old/new); `get_item(db, item_id) -> Item | None`; `list_items(db) -> list[Item]`; `set_assignments(db, actor: str, item_id: str, targets: list[tuple[TargetKind, str]]) -> None` (audited); `get_assignments(db, item_id) -> list[tuple[TargetKind, str]]`; `set_item_entities(db, item_id: str, entity_ids: list[str]) -> None`; `items_containing(db, entity_id: str) -> list[str]`; `seed_builtins(db) -> None` — idempotent; creates the sections `section:devices`, `section:automations`, `section:scripts`, `section:dashboards`, `section:users`, `section:system`, `section:audit`, `section:signin_log`, `section:run_history`, the features `feature:test_center`, `feature:api_tokens`, and the dashboard `dashboard:home`. All are `builtin=True`, `restrict`, `others_see="none"`, with the spec's starting role assignments (operator → devices, automations, scripts, dashboards, test_center; household → dashboard:home; auditor → audit, signin_log, run_history).
- Produces in `evaluate.py`: `evaluate(db, p: Principal, item: Item, client_ip: IPAddress, local_ranges: Sequence[str], purpose: Literal["use", "manage"] = "use") -> Decision`, implementing the spec's five steps exactly:
  1. `not p.active` → `Decision(False, False)`.
  2. `p.is_admin` → `manage`: allow. `use`: allow unless `item.status == "disabled"`. Listed: always.
  3. `status == "disabled"` → deny; listed only if `visibility == "show"` or the principal is assigned (shown as disabled).
  4. `network == "local"` and not `is_local(client_ip)` → deny, listed as locked.
  5. `show` → allow. `hide` → deny, not listed. `restrict` → allow if assigned via user / any group / role / screen id; otherwise deny, `listed = others_see == "locked"`.

  Non-admin `manage` follows the same rule as `use`: access is binary.

- [ ] **Step 1: Write failing tests** — a table-driven `test_evaluate` with one row per case, plus the network tests:

```python
CASES = [  # (principal, item overrides, assignments, ip, expected Decision)
    ("sam", {}, [], LAN, Decision(False, True)),                                  # default restrict → locked
    ("sam", {"others_see": "none"}, [], LAN, Decision(False, False)),
    ("sam", {}, [("user", "sam")], LAN, Decision(True, True)),
    ("sam", {}, [("group", "family")], LAN, Decision(True, True)),                # sam ∈ family
    ("sam", {}, [("role", "household")], LAN, Decision(True, True)),
    ("sam", {"visibility": "hide"}, [("user", "sam")], LAN, Decision(False, False)),
    ("sam", {"visibility": "show"}, [], LAN, Decision(True, True)),
    ("sam", {"status": "disabled", "visibility": "show"}, [], LAN, Decision(False, True)),
    ("sam_disabled", {"visibility": "show"}, [], LAN, Decision(False, False)),
    ("garage_tablet", {"network": "local"}, [("screen", "garage")], LAN, Decision(True, True)),
    ("garage_tablet", {"network": "local"}, [("screen", "garage")], WAN, Decision(False, True)),
    ("other_tablet", {"network": "local"}, [("screen", "garage")], LAN, Decision(False, True)),
    ("admin", {"visibility": "hide"}, [], WAN, Decision(True, True)),
    ("admin", {"status": "disabled"}, [], LAN, Decision(False, True)),
]

def test_admin_can_manage_disabled_item(db, admin): ...   # purpose="manage" → allowed
def test_token_never_exceeds_owner(db): ...               # token principal built from sam == sam's decisions
def test_spoofed_xff_from_untrusted_peer_ignored():       # Review Focus 1
    assert str(resolve_client_ip("203.0.113.9", "192.168.1.5", ["192.168.1.1/32"])) == "203.0.113.9"
def test_xff_from_trusted_proxy_used():
    assert str(resolve_client_ip("192.168.1.1", "203.0.113.9, 192.168.1.1", ["192.168.1.1/32"])) == "203.0.113.9"
def test_ipv4_mapped_ipv6_is_local():                     # Review Focus 2
    assert is_local(resolve_client_ip("::ffff:192.168.1.5", None, []), ["192.168.1.0/24"])
def test_seed_builtins_idempotent_and_assigned(db): ...   # run twice; operator assigned section:scripts; household dashboard:home
```

`LAN = ip_address("192.168.1.5")`, `WAN = ip_address("203.0.113.9")`, local ranges `["192.168.1.0/24"]`. Screen principals are built directly in tests (`Principal(kind="screen", id="garage", user_id=None, role=None, group_ids=frozenset(), active=True)`) until Plan 2 adds enrollment.

- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement the four modules.
- [ ] **Step 4:** Rerun. Expected: PASS, all rows.
- [ ] **Step 5: Commit** `git commit -s -m "feat(access): items, assignments, network check and evaluate()"`

---

### Task 7: Command guard and save guard

**Files:**
- Modify: `core/cave/access/evaluate.py`
- Create: `core/cave/api/entities.py` (command route only in this task)
- Test: `core/tests/test_guards.py`

**Interfaces:**
- Consumes: `evaluate`, `items_containing`, `StateMachine.command`, `deps`.
- Produces:
  - `can_control(db, p: Principal, entity_id: str, client_ip, local_ranges) -> bool` — True if `p.is_admin` and `p.active`, or if any item in `items_containing(entity_id)` evaluates `allowed` for `use`.
  - `class AccessDenied(Exception)`; `assert_can_save(db, p: Principal, targeted_entity_ids: Iterable[str], client_ip, local_ranges) -> None` — raises `AccessDenied` listing the entities `p` can't control. (Plan 4 calls this when saving automations, sequences, scripts and dashboards.)
  - `deps.current_principal(request) -> Principal` (session cookie or `Authorization: Bearer` token; screens arrive in Plan 2), and `deps.client_ip(request) -> IPAddress` using `resolve_client_ip` with `request.client.host`, `X-Forwarded-For` and `Settings.trusted_proxies`.
  - `POST /api/v1/entities/{entity_id}/commands/{command}` (JSON body = args) → `202`; `403 {"detail": "You don't have access to this control."}` when `can_control` is False; `404` for an unknown entity.

- [ ] **Step 1: Write failing tests** — the spec's garage scenario. Items: `dashboard:garage` containing `cover.garage_door`, assigned only to `("screen", "garage")`, network `local`; `dashboard:kids` containing `light.kids_room`, assigned to group `kids`; sam ∈ kids.

```python
def test_kids_dashboard_cannot_open_garage(...):
    assert not can_control(db, sam, "cover.garage_door", LAN, LOCAL)
    assert can_control(db, sam, "light.kids_room", LAN, LOCAL)

def test_command_route_refuses_and_does_not_call_handler(client_as_sam, handler_spy):
    r = client_as_sam.post("/api/v1/entities/cover.garage_door/commands/open", json={})
    assert r.status_code == 403 and handler_spy.calls == []

def test_other_users_token_cannot_command(client, sam_token): ...  # Bearer sam_token → 403 on garage
def test_save_guard_blocks_back_door(db, operator):
    with pytest.raises(AccessDenied) as e:
        assert_can_save(db, operator, ["cover.garage_door"], LAN, LOCAL)
    assert "cover.garage_door" in str(e.value)
def test_admin_can_save_anything(db, admin): ...
```

- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Rerun. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "feat(access): command guard and editor save guard"`

---

### Task 8: Filtered reads over REST

**Files:**
- Modify: `core/cave/api/entities.py`
- Test: `core/tests/test_reads.py`

**Interfaces:**
- Produces:
  - `entity_view(db, p, entity: Entity, state: State | None, client_ip, local_ranges) -> dict[str, Any]` — the full view `{"entity_id", "name", "area_id", "capability", "state", "attributes", "last_changed"}` when `can_control`, otherwise exactly `{"entity_id", "name", "area_id", "restricted": True}`.
  - `GET /api/v1/states` → `list[entity_view]` for every registered entity. `GET /api/v1/states/{entity_id}` → one view.

- [ ] **Step 1: Write failing tests:** `test_restricted_entity_is_stub` (sam's `GET /states` row for `cover.garage_door` equals the stub exactly, so no `state` key leaks); `test_controllable_entity_is_full` (`light.kids_room` has `state`); `test_admin_sees_everything_full`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Rerun. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "feat(api): filtered state reads with restricted stubs"`

---

### Task 9: WebSocket with live, filtered state

**Files:**
- Create: `core/cave/api/ws.py`
- Test: `core/tests/test_ws.py`

**Interfaces:**
- Consumes: `EventBus`, `can_control`, `current_principal` (session cookie at handshake), `entity_view`.
- Produces: `/api/v1/ws`. Client messages follow the framework's shape: `{"id", "type": "subscribe", "events": ["state_changed"]}` and `{"id", "type": "command", "entity_id", "command", "args"}`. The server sends `{"id", "type": "event", "event": {...}}` only for entities the principal can control at the moment the event is sent. Commands go through the same check as the REST route and return `{"id", "type": "result", "success": bool, "error"?: str}`.
- Produces on the bus, for later plans and Task 10: `{"type": "access_changed"}` (any item, assignment, group or user change) and `{"type": "principal_disabled", "user_id"}`. On `access_changed`, each socket re-evaluates its principal. On `principal_disabled` for its user, it closes with code `4401`.

- [ ] **Step 1: Write failing tests:**
  - `test_events_filtered` (sam subscribes; `set("cover.garage_door", "open")` and then `set("light.kids_room", "on")`; the first message sam receives is for `light.kids_room`)
  - `test_entity_removed_from_item_stops_events` — Review Focus 4 (`set_item_entities("dashboard:kids", [])`, publish `access_changed`, `set("light.kids_room", "off")`: sam gets no event; `GET /states/light.kids_room` returns the stub)
  - `test_disabled_user_socket_closes` — Review Focus 3 (publish `principal_disabled` for sam: the socket closes with 4401)
  - `test_ws_command_respects_guard`
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement. Cache `can_control` results per socket and clear the cache on `access_changed`.
- [ ] **Step 4:** Rerun. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "feat(api): websocket with per-principal filtering"`

---

### Task 10: Access admin API, groups, last-Admin rule

**Files:**
- Create: `core/cave/api/admin.py`
- Modify: `core/cave/auth/users.py` (update/disable with guard), `core/cave/api/app.py` (call `seed_builtins` on startup)
- Test: `core/tests/test_admin_api.py`

**Interfaces:**
- Consumes: `evaluate` with `purpose="manage"` on `section:users` (and `section:audit` for audit reads), `items.*`, `audit.*`, `sessions.end_for_user`, the bus events from Task 9.
- Produces (all under `/api/v1`, each change audited and followed by an `access_changed` publish):
  - `GET/POST /users`, `PATCH /users/{id}` (`display_name`, `role`, `enabled`, `expires_at`). Disabling a user ends their sessions and publishes `principal_disabled`.
  - `GET/POST /groups`, `PUT /groups/{id}/members` (`list[user_id]`), `DELETE /groups/{id}`.
  - `GET /items` (only items `listed` for the caller, each with its `allowed`), `PATCH /items/{id}` (`status`, `visibility`, `others_see`, `network`), `GET/PUT /items/{id}/assignments` (`list[{"kind", "id"}]`).
  - `GET /audit?limit=`.
  - `class LastAdminError(Exception)` → HTTP `409 {"detail": "CAVE needs at least one enabled Admin."}`.
  - Built-in items can't be deleted. `PATCH` on them is allowed.

- [ ] **Step 1: Write failing tests:**
  - `test_last_admin_cannot_be_disabled_or_demoted` (two PATCHes → 409; after a second admin is created, it succeeds)
  - `test_operator_cannot_manage_users` (403)
  - `test_item_patch_is_audited_with_old_and_new`
  - `test_assignment_change_takes_effect_immediately` (sam gets 403 on a command, the admin assigns, then sam gets 202, with no re-login)
  - `test_get_items_respects_others_see` (sam's list shows a locked item with `allowed: false` and omits an `others_see="none"` item)
  - `test_auditor_reads_audit_but_cannot_patch_items`
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Rerun. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "feat(api): access administration, groups, last-admin rule"`

---

### Task 11: API tokens

**Files:**
- Create: `core/cave/auth/tokens.py`
- Modify: `core/cave/api/admin.py`, `core/cave/api/deps.py`
- Test: `core/tests/test_tokens.py`

**Interfaces:**
- Produces: `tokens.create(db, actor: str, user_id: str, name: str) -> str` (it returns `cave_` + `secrets.token_urlsafe(32)` once and stores only its SHA-256); `tokens.lookup(db, raw: str) -> str | None` (owner user_id when the token isn't revoked); `tokens.revoke(db, actor, token_id) -> None`. Routes: `POST /api/v1/tokens` (needs `feature:api_tokens` allowed for the caller), `GET /api/v1/tokens` (the caller's own; Admins see all), `DELETE /api/v1/tokens/{id}`. In `current_principal`, a Bearer token builds `Principal(kind="token", ...)` from its owner. A disabled owner makes it inactive.
- [ ] **Step 1: Write failing tests:**
  - `test_token_acts_as_owner` (sam's token can command `light.kids_room` but not the garage)
  - `test_token_stored_hashed` (the raw value isn't in the DB)
  - `test_revoked_token_401`
  - `test_disabled_owner_token_denied`
  - `test_create_requires_feature` (household without `feature:api_tokens` → 403)
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Rerun. Expected: PASS, plus the full suite and `ruff` / `mypy --strict` clean.
- [ ] **Step 5: Commit** `git commit -s -m "feat(auth): api tokens that act as their owner"`

---

## Plan 1 done when

- CI is green: ruff, mypy --strict, pytest.
- The garage scenario's server-side refusals pass in tests for: a household member, an unenrolled principal, an off-network request on a `local` item, another user's token, and a command through the Kids dashboard. (The enrolled-tablet cases arrive with Plan 2.)
- Plan 2 and Plan 3 can start in parallel.
