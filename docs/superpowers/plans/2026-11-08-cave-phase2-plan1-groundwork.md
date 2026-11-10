# CAVE Phase 2, Plan 1: Integration Groundwork — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The shared pieces every batch 1 integration needs: encrypted credentials, one way to add and remove devices, a defined set of media, number and choice controls, and those controls on dashboard tiles.

**Architecture:**
- **Credentials:** encrypted with AES-GCM under a host key. The key is a Compose secret file the installer creates; in development it's a file next to the database.
- **Integrations:** each implements one `Integration` protocol. A registry loads their added devices from a single `integration_devices` table and serves one generic API, so each later plan only writes the device client.
- **Controls:** commands are validated in one place, `cave.controls`, before an integration's handler sends them. Dashboard tiles show media, number and choice controls.

**Tech Stack:** Python 3.13, FastAPI, `cryptography` (already a dependency) for AES-GCM, SQLite migrations; React 19, Fluent UI v9, TanStack Query.

**Spec:** `docs/superpowers/specs/2026-11-08-cave-phase2-design.md` (sections "How an integration fits in", "Credentials", "Constraints", "Anti-goals").

**Where this plan sits.** Phase 2 has six plans, written one at a time; each is written once the one before it is done:
1. **Groundwork** (this plan).
2. HTTP devices: Shelly, WLED, Philips Hue, Fully Kiosk.
3. Sensors and ESPHome: System monitor, AirVisual Pro, NUT, ESPHome native API.
4. TVs: Apple TV, Sony Bravia.
5. Notifications: ntfy (including the optional add-on and its iOS relay, labeled Cloud) and email (SMTP).
6. **Find devices** in the setup wizard, and the Phase 2 exit gate.

## Global Constraints

- Tests never touch real devices or the network (`CLAUDE.md`). Integrations are tested with fakes.
- Integration settings live in the database, not in `/config` files.
- Every add, remove or credential change is written to the audit log with old and new values, secrets masked.
- Credentials are never stored in plain text, never logged, and never sent back to the browser. A form shows that a value is set, not what it is.
- Every command goes through `can_control`, like MQTT and Kasa today.
- No GPL library in the core.
- A device's stable identity is its MAC address or serial number, never its IP address.
- Run from `core/`: `ruff check .`, `mypy --strict cave`, `pytest`. From `console/`: `pnpm lint`, `pnpm test`.
- Commits: Conventional Commits, `git commit -s`.

## Review Focus

1. **The host key is lost or replaced** (a restore without `secrets/host_key`, a fresh install over old data). CAVE must still start. Undecryptable credentials read as not set, and their devices read as unavailable until re-paired. Never crash, never log key material. Pinned in Tasks 1 and 2.
2. **A device comes back at a new address.** Adding a device whose `device_id` already exists updates its host instead of creating a duplicate or failing. Pinned in Task 2.
3. **The probe address as a way to reach other machines.** `probe` and `add` make CAVE connect to an address someone typed. Only IP literals inside the configured local ranges are accepted; hostnames, public addresses and loopback are refused. Pinned in Task 2.
4. **A secret leaking through a side channel:** API responses, audit entries or log lines. Pinned in Tasks 1 and 2 by asserting the secret's text appears nowhere.
5. **A device that never answers.** A probe that hangs must stop after `PROBE_SECONDS` with a plain message, not tie up the request. One device failing to attach at startup must not stop the others. Pinned in Task 2.

---

### Task 1: Host key and encrypted credentials

**Files:**
- Create: `core/cave/credentials.py`
- Create: `core/cave/migrations/0009_integrations.sql` (both tables for this plan; Task 2 uses the second)
- Modify: `core/cave/api/app.py` (create `app.state.credentials` in `create_app`)
- Modify: `compose.yaml` (secret `host_key`, `CAVE_HOST_KEY_FILE: /run/secrets/host_key` on `cave`)
- Modify: `deploy/install.sh` (`new_secret secrets/host_key "$CORE_UID"` next to the other two)
- Modify: `docs/install/debian.md` (back up `secrets/host_key` with the data folder; without it, saved device passwords and keys must be entered again)
- Test: `core/tests/test_credentials.py`

**Interfaces:**
- Produces:
  - `load_host_key(db_path: Path, environ: Mapping[str, str] = os.environ) -> bytes`: returns 32 bytes. Source order: `env_secret("CAVE_HOST_KEY", environ)` as 64 hex characters, otherwise `db_path.parent / "host_key"`, created with mode 0600 holding 64 hex characters if missing. A malformed value raises `SystemExit` naming the variable or file, never the value.
  - `class Credentials(db: Database, key: bytes)`:
    - `set(integration: str, name: str, value: str, actor: str) -> None`
    - `get(integration: str, name: str) -> str | None`: `None` when missing or undecryptable
    - `is_set(integration: str, name: str) -> bool`
    - `delete(integration: str, name: str, actor: str) -> None`
    - `delete_prefix(integration: str, prefix: str, actor: str) -> None`: removes every name starting with `prefix`; used when a device is removed
  - Audit actions `credential.set` and `credential.delete`, target `credential:<integration>:<name>`, old and new values `{"set": bool}` only.

Migration `0009_integrations.sql`:

```sql
-- Secrets CAVE must read back (pairing keys, passwords). AES-GCM under the host key; never plain text.
CREATE TABLE credentials (
    integration TEXT NOT NULL,
    name TEXT NOT NULL,
    nonce BLOB NOT NULL,
    ciphertext BLOB NOT NULL,
    PRIMARY KEY (integration, name)
);

-- Devices an Admin added through any Phase 2 integration. device_id is the MAC or serial: an address can change.
CREATE TABLE integration_devices (
    integration TEXT NOT NULL,
    device_id TEXT NOT NULL,
    host TEXT NOT NULL,
    model TEXT NOT NULL,
    name TEXT NOT NULL,
    settings TEXT NOT NULL DEFAULT '{}',  -- JSON, never secrets
    PRIMARY KEY (integration, device_id)
);
```

- [ ] **Step 1: Write the failing tests** in `core/tests/test_credentials.py`:
  - `test_round_trip`: `set("hue", "abc:app_key", "s3cret-value", "user:admin")`, then `get` returns `"s3cret-value"` and `is_set` is `True`.
  - `test_stored_encrypted`: the raw `ciphertext` and `nonce` columns don't contain `b"s3cret-value"`.
  - `test_rows_cannot_be_swapped`: copy one row's `nonce` and `ciphertext` onto another name. `get` on that name returns `None`, because associated data is `f"{integration}:{name}"`.
  - `test_wrong_key_reads_as_not_set`: write with one key and read with another. Expect `None`, and `caplog` holds a warning naming `hue:abc:app_key` but neither key's hex nor the value.
  - `test_audit_masks_value`: the newest audit entry is `credential.set` with `new == {"set": True}`, and `"s3cret-value"` appears nowhere in `audit.list_entries`.
  - `test_delete_prefix`: after `delete_prefix("hue", "abc:", ...)`, every `abc:*` name is gone and `other:*` remains.
  - `test_host_key_file_created_once` (`tmp_path`, empty environ): the first call creates `host_key` with 64 hex characters. On POSIX its mode is `0o600`; skip that assertion on Windows. A second call returns the same bytes.
  - `test_host_key_from_env_file`: `CAVE_HOST_KEY_FILE` points at a file of 64 hex characters, and that key wins over the data-folder file.
  - `test_malformed_host_key_exits`: `CAVE_HOST_KEY="nothex"` raises `SystemExit`, and the message contains `CAVE_HOST_KEY` but not `nothex`.
  - In `core/tests/test_install_script.py`, add `"host_key"` to the names `test_secret_files_private` loops over (it must exist, be private and hold 64 hex characters). `test_rerun_changes_nothing` then covers it on a re-run.
  - In `core/tests/test_deploy_files.py`, add `test_core_gets_host_key_as_a_secret`: in `compose.yaml`, the `cave` service lists `host_key` under `secrets` and sets `CAVE_HOST_KEY_FILE: /run/secrets/host_key`, and no service puts it in `environment` as a value.

- [ ] **Step 2: Run them and see them fail**

Run: `pytest tests/test_credentials.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cave.credentials'`.

- [ ] **Step 3: Implement `cave/credentials.py` and the migration**

Use `cryptography.hazmat.primitives.ciphers.aead.AESGCM`, a fresh 12-byte nonce per `set`, and associated data `f"{integration}:{name}".encode()`. Catch `InvalidTag` in `get`: log a warning, return `None`. Write the file key with `os.open(..., O_CREAT | O_EXCL | O_WRONLY, 0o600)`.

- [ ] **Step 4: Wire it in.** In `create_app`, set `app.state.credentials = Credentials(app.state.db, load_host_key(settings.db_path))`. Add the Compose secret, the installer line and the install-guide note listed under Files.

- [ ] **Step 5: Run the tests and the suite**

Run: `pytest tests/test_credentials.py -v && pytest -q && ruff check . && mypy --strict cave`
Expected: all pass, including the installer and Compose tests above.

- [ ] **Step 6: Commit**

```bash
git add core/cave/credentials.py core/cave/migrations/0009_integrations.sql core/cave/api/app.py core/tests/test_credentials.py core/tests/test_install_script.py core/tests/test_deploy_files.py compose.yaml deploy/install.sh docs/install/debian.md
git commit -s -m "feat: encrypted credentials under a host key"
```

### Task 2: Integration registry and the devices API

**Files:**
- Create: `core/cave/integrations/base.py`
- Create: `core/cave/api/integrations.py`
- Modify: `core/cave/api/app.py` (create `app.state.integrations`, call `load()` in `create_app`, run and cancel `run()` in `lifespan` like the Kasa task, `include_router`)
- Create: `core/tests/fake_integration.py` (a `FakeIntegration` that records calls, with a settable answer per host)
- Test: `core/tests/test_integrations_api.py`

**Interfaces:**
- Consumes: `Credentials` (Task 1); `cave.access.network.is_local`; `cave.api.admin._require`, `_actor`; `cave.audit.record`.
- Produces (in `cave/integrations/base.py`):

```python
Pairing = Literal["none", "password", "key", "pin", "button"]
PROBE_SECONDS = 5.0

@dataclass(frozen=True)
class Found:
    device_id: str  # MAC (lowercase hex, no separators) or serial
    host: str
    model: str
    name: str

@dataclass(frozen=True)
class Device:
    integration: str
    device_id: str
    host: str
    model: str
    name: str
    settings: dict[str, Any]

class PairingError(Exception): ...  # its message is shown to the Admin as is

class Integration(Protocol):
    domain: str        # "hue", "shelly", ...
    title: str         # "Philips Hue"
    pairing: Pairing
    pairing_hint: str  # one sentence: where the PIN, key or button is
    async def probe(self, host: str) -> Found | None: ...
    async def pair(self, host: str, secret: str | None) -> tuple[Found, dict[str, str]]: ...  # credentials to keep
    def attach(self, device: Device) -> None: ...  # register entities, start talking to it
    def detach(self, device_id: str) -> None: ...  # unregister entities, stop
    async def run(self) -> None: ...               # background loop; cancelled on shutdown

class Integrations:
    def __init__(self, db: Database, credentials: Credentials) -> None: ...
    def register(self, integration: Integration) -> None: ...
    def get(self, domain: str) -> Integration | None: ...
    def all(self) -> list[Integration]: ...
    def devices(self, domain: str) -> list[Device]: ...
    def load(self) -> None: ...  # attach every stored device; one failure is logged and skipped
    async def run(self) -> None: ...  # gather every integration's run()
    async def probe(self, domain: str, host: str) -> Found | None: ...  # asyncio.wait_for(..., PROBE_SECONDS)
    async def add(self, domain: str, host: str, secret: str | None, actor: str) -> tuple[Device, bool]: ...  # (device, created)
    def remove(self, domain: str, device_id: str, actor: str) -> None: ...  # KeyError if missing
```

Credentials an integration returns from `pair` are stored as `credentials.set(domain, f"{device_id}:{key}", value, actor)`. An integration reads them back as `credentials.get(domain, f"{device_id}:{key}")`.

Routes in `cave/api/integrations.py`, prefix `/api/v1/integrations`. Each starts with `_require(request, p, "section:devices")`.

| Route | Body | Answer |
|---|---|---|
| `GET ""` | | `[{domain, title, pairing, pairing_hint, devices: [{device_id, host, model, name}]}]` |
| `POST "/{domain}/probe"` | `{host}` | `200 {device_id, host, model, name, added: bool}`; `404 "Nothing CAVE recognizes answered at that address."` (also after `PROBE_SECONDS`) |
| `POST "/{domain}/devices"` | `{host, secret: str \| None}` | `201` new device, or `200` when the `device_id` already existed and only its host changed; `422` with a `PairingError` message |
| `DELETE "/{domain}/devices/{device_id}"` | | `204`; `404 "No such device."` |

Unknown `domain` gives `404 "No such integration."`. `host` must parse as an IP address and pass `is_local(ip, local_ranges)`; loopback is refused even if a range includes it. Otherwise answer `422 "Use the device's address on your home network, like 192.168.1.40."`. Audit actions: `integration.add` (new value: the device without settings), `integration.update` (old and new host), `integration.remove` (old value: the device).

- [ ] **Step 1: Write `tests/fake_integration.py` and the failing tests** in `core/tests/test_integrations_api.py`, using `lan_client`/`sign_in` from `conftest` and registering `FakeIntegration(domain="fake", pairing="key")` on `app.state.integrations`:
  - `test_lists_integrations_with_devices`: after an add, `GET` shows `{"domain": "fake", "pairing": "key", "devices": [{"device_id": "aabbccddeeff", ...}]}` and no `secret` key anywhere in the JSON.
  - `test_probe_found_and_not_found`: the fake answers for `192.168.1.40`, giving 200 with `added: false`. `192.168.1.41` gives 404 with the exact message.
  - `test_probe_times_out`: monkeypatch `base.PROBE_SECONDS = 0.05` and have the fake sleep for 1 second. Expect 404 in under 1 second.
  - `test_add_stores_device_credential_and_audit`: 201. `credentials.get("fake", "aabbccddeeff:key") == "pair-secret-123"`. The newest audit entry is `integration.add`, and `"pair-secret-123"` is absent from every audit entry, the response body and `caplog.text`.
  - `test_add_same_device_new_address_updates_host`: add at `.40`, then at `.42` with the same `device_id`. Expect 200, one row, host `.42`, an `integration.update` audit entry, and the fake's `attach` called again with the new host.
  - `test_pairing_error_is_422_with_message`: the fake raises `PairingError("Press the button on the bridge first.")`. Expect 422 with that detail and no row stored.
  - `test_refuses_non_local_hosts`: `"8.8.8.8"`, `"127.0.0.1"`, `"bridge.local"` and `"192.168.1.40:80"` each give 422 with the exact message, and the fake's `probe` is never called.
  - `test_remove_detaches_and_deletes_credentials`: 204; the fake recorded `detach`; `credentials.is_set` is `False`; the audit entry is `integration.remove`.
  - `test_needs_devices_section`: `sam` (household) gets 403 on every route.
  - `test_load_attaches_stored_devices_and_survives_one_failure`: two stored devices, and the fake's `attach` raises for the first. After `load()`, the second is attached and the log names the first device's id.

- [ ] **Step 2: Run and see them fail**

Run: `pytest tests/test_integrations_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cave.integrations.base'`.

- [ ] **Step 3: Implement `cave/integrations/base.py`, `cave/api/integrations.py` and the app wiring** with the interfaces above. `settings` round-trips as JSON in the `settings` column.

- [ ] **Step 4: Run the tests and the suite**

Run: `pytest tests/test_integrations_api.py -v && pytest -q && ruff check . && mypy --strict cave`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add core/cave/integrations/base.py core/cave/api/integrations.py core/cave/api/app.py core/tests/fake_integration.py core/tests/test_integrations_api.py
git commit -s -m "feat: one registry and API for adding integration devices"
```

### Task 3: The control vocabulary

**Files:**
- Create: `core/cave/controls.py`
- Test: `core/tests/test_controls.py`

**Interfaces:**
- Produces:
  - `check_command(capability: str, command: str, args: Mapping[str, Any], attributes: Mapping[str, Any]) -> dict[str, Any]`: returns the cleaned args, or raises `ValueError` with a sentence a person can read. The existing route turns that into a 409. Every later integration calls it first in its command handler.
  - The state and attribute conventions below, which later plans' integrations must follow.

| Capability | State values | Attributes | Commands and args |
|---|---|---|---|
| `media_player` | `off`, `on`, `idle`, `playing`, `paused` | `volume` (0–100), `muted`, `source`, `sources` (list), `app` | `turn_on`, `turn_off`, `toggle`, `play`, `pause`, `play_pause`, `volume_set {level: int 0–100}`, `volume_mute {muted: bool}`, `select_source {source}` (must be in `sources`) |
| `number` | the value as text | `min`, `max`, `step`, `unit` | `set_value {value}`: a number from `min` to `max`, snapped to `step` |
| `select` | the chosen option | `options` (list) | `select_option {option}` (must be in `options`) |

Capabilities not in the table (`switch`, `light` and the rest) pass through unchanged, so MQTT and Kasa behave as before.

- [ ] **Step 1: Write the failing tests** in `core/tests/test_controls.py`:
  - `test_media_commands_accepted`: each media command with valid args returns its args. `volume_set {"level": "35"}` returns `{"level": 35}`.
  - `test_media_bad_args_refused`: `volume_set {"level": 101}` raises `ValueError` matching `"0 to 100"`. `select_source {"source": "HDMI 9"}` with `sources ["HDMI 1"]` raises matching `"HDMI 9"`. `"rewind"` raises matching `"can't"`.
  - `test_number_snaps_and_bounds`: with `min 0, max 255, step 5`, `{"value": 12}` returns `{"value": 10}`, and `{"value": 300}` raises.
  - `test_select_option_must_exist`: `options ["Rainbow", "Fire"]`; `"Fire"` is accepted, `"Ice"` raises.
  - `test_other_capabilities_unchanged`: `check_command("switch", "turn_on", {}, {}) == {}`.

- [ ] **Step 2: Run and see them fail**

Run: `pytest tests/test_controls.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cave.controls'`.

- [ ] **Step 3: Implement `check_command`** as a table per capability.

- [ ] **Step 4: Run**

Run: `pytest tests/test_controls.py -v && ruff check . && mypy --strict cave`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/cave/controls.py core/tests/test_controls.py
git commit -s -m "feat: one vocabulary for media, number and choice controls"
```

### Task 4: Media, number and choice controls on tiles

**Files:**
- Create: `console/src/cards/controls.tsx`
- Modify: `console/src/cards/Tile.tsx` (render `<Controls entity={...} />` under the state when the entity isn't restricted and its capability is `media_player`, `number` or `select`)
- Test: `console/src/cards/controls.test.tsx`

**Interfaces:**
- Consumes: the Task 3 table (commands, args, attributes); `POST /entities/{id}/commands/{command}` with a JSON body for args.
- Produces: `export function Controls({ entity }: { entity: EntityView })`.

| Capability | Controls | Accessible name |
|---|---|---|
| `media_player` | power button (`turn_on` or `turn_off` by state); play/pause button when the state is `playing` or `paused`; volume slider when `volume` is present, sent on release; source dropdown when `sources` is present | "Power", "Pause" / "Play", "Volume", "Source" |
| `number` | slider over `min`–`max` by `step`, showing the value with `unit`, sent on release | the entity's name |
| `select` | dropdown of `options` | the entity's name |

A failed command shows the server's message under the tile, the way the toggle does today.

- [ ] **Step 1: Write the failing tests** in `console/src/cards/controls.test.tsx`, using `mockApi` and `renderWith`:
  - `"pauses a playing TV"`: state `playing`. Clicking "Pause" posts `/entities/media_player.living_tv/commands/pause`.
  - `"turns an off TV on"`: state `off`. "Power" posts `turn_on`, and there's no "Pause" or "Play".
  - `"sets volume on release"`: changing "Volume" to 40 posts `volume_set` with `{ level: 40 }` once.
  - `"applies a preset"`: select entity with `options ["Rainbow", "Fire"]`. Choosing "Fire" posts `select_option` with `{ option: "Fire" }`.
  - `"shows no controls for a restricted device"`: `{restricted: true}` renders no button or slider.
  - `"shows the server's refusal"`: a 409 with `"This device can't take commands right now."` shows that text.
  - `"is accessible"`: `expectAccessible(container)`.

- [ ] **Step 2: Run and see them fail**

Run: `pnpm vitest run src/cards/controls.test.tsx`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `Controls`** with Fluent `Button`, `Slider` and `Dropdown`. Send slider changes on release, not on every move.

- [ ] **Step 4: Run**

Run: `pnpm lint && pnpm test`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add console/src/cards/controls.tsx console/src/cards/Tile.tsx console/src/cards/controls.test.tsx
git commit -s -m "feat(console): media, number and choice controls on tiles"
```

### Task 5: One Add device panel for every integration

**Files:**
- Create: `console/src/admin/AddIntegration.tsx`
- Modify: `console/src/admin/AddDevice.tsx` (the Kasa section stays first; below it, one row per integration from `GET /integrations`, each opening `AddIntegration`)
- Modify: `console/src/admin/AddDevice.test.tsx`
- Create: `docs/integrations/README.md` (how adding works for every integration; links each integration's page as later plans add them)

**Interfaces:**
- Consumes: the Task 2 routes.
- Produces: `export function AddIntegration({ integration, onDone }: { integration: IntegrationInfo; onDone: () => void })`, where `IntegrationInfo = { domain, title, pairing, pairing_hint, devices: {device_id, host, model, name}[] }`. Add it to `console/src/api/types.ts`.

Flow:
1. "Device address" field (`inputMode="decimal"`, `spellCheck={false}`, placeholder `192.168.1.40…`), then **Check**, which calls `probe`.
2. A found device shows its model and name.
3. The pairing step by `pairing`:
   - `password`, `key`, `pin`: a masked input labeled by kind ("Password", "Encryption key", "PIN"), with `pairing_hint` as its hint and `autoComplete="off"`.
   - `button`: `pairing_hint` as an instruction, with no input.
   - `none`: nothing.
4. **Add**, which posts `devices`. The button stays enabled until the request starts.

Each added device is listed with **Remove**, which asks for confirmation in a dialog before calling `DELETE`. Errors show inline under the field they belong to.

- [ ] **Step 1: Write the failing tests** in `AddDevice.test.tsx`, using `mockApi` for `/integrations`, probe and add:
  - `"lists every integration"`: "Philips Hue" and "Shelly" rows appear under the Kasa section.
  - `"checks an address then adds with a key"`: type `192.168.1.40`, then Check. "Hue Bridge" appears. Enter the key, then Add. The post body is `{ host: "192.168.1.40", secret: "the-key" }`.
  - `"button pairing shows the hint and no input"`: `pairing: "button"` shows the hint text and no textbox labeled "Encryption key".
  - `"shows a refused address inline"`: a 422 detail shows under "Device address".
  - `"asks before removing"`: Remove opens a dialog, and `DELETE` is sent only after confirming.
  - `"never shows a saved secret"`: no input holds a value after reopening the panel for a device that was added.
  - `"is accessible"`.

- [ ] **Step 2: Run and see them fail**

Run: `pnpm vitest run src/admin/AddDevice.test.tsx`
Expected: the new tests fail; the existing Kasa tests still pass.

- [ ] **Step 3: Implement `AddIntegration` and the list in `AddDevice`, and write `docs/integrations/README.md`.**

- [ ] **Step 4: Run**

Run: `pnpm lint && pnpm test`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add console/src/admin/AddIntegration.tsx console/src/admin/AddDevice.tsx console/src/admin/AddDevice.test.tsx console/src/api/types.ts docs/integrations/README.md
git commit -s -m "feat(console): add and remove devices for any integration"
```

## Plan 1 done when

- `pytest`, `ruff check .` and `mypy --strict cave` pass from `core/`, and `pnpm lint` and `pnpm test` pass from `console/`.
- With `FakeIntegration` registered, an Admin can check an address, add a device with a key, see it listed, and remove it. The key is stored encrypted, never shown again, and absent from audit entries and logs.
- A re-run of `deploy/install.sh` on an existing install creates `secrets/host_key` without touching anything else.
