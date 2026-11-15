# CAVE Phase 2, Plan 2: HTTP Devices — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** WLED, Shelly, Philips Hue and Fully Kiosk Browser devices can be added from Devices → Add device and used as CAVE entities on dashboards, in automations and under access control.

**Architecture:**
- **One small HTTP client** (`cave/integrations/http.py`) on the standard library, like Kasa's: JSON in and out, a hard timeout, a size cap, and errors that never contain the request path (Hue keys and Fully Kiosk passwords travel in it).
- **Four integrations**, each one package implementing plan 1's `Integration` protocol and registered in `create_app`. Each takes its HTTP function as a constructor argument, so tests pass a fake device instead.
- **Lights follow the MQTT convention already in the code:** attribute `brightness` 0–255, `turn_on` takes an optional `brightness`. `cave.controls` gains a `light` table, and light tiles gain a brightness slider.

**Tech Stack:** Python 3.13 standard library (`http.client`, `asyncio.to_thread`), FastAPI; React 19, Fluent UI v9. No new dependency.

**Spec:** `docs/superpowers/specs/2026-11-08-cave-phase2-design.md` (sections "Batch 1", "How an integration fits in", "Constraints", "Anti-goals").

**Where this plan sits.** Plan 2 of six. Plan 1 (groundwork) is merged: the registry in `core/cave/integrations/base.py`, encrypted `Credentials`, the generic `/api/v1/integrations` routes, the Add device panel, and `check_command` called from `StateMachine.command`.

## Decisions (builder's calls; the spec leaves command sets and polling to the builder)

- **Polling every 15 seconds,** not push. Shelly's WebSocket and Hue's event stream can replace it later without changing entities.
- **Brightness, not colour,** for Hue and WLED lights. Colour needs a colour control on tiles, which doesn't exist yet; it goes in a later plan.
- **Shelly:** relay channels as `switch`es, with power and energy `sensor`s where the device reports them. Shelly dimmers and RGBW lights, and Shelly devices with a password set, are refused with a plain message for now.
- **Hue:** the bridge's v1 local API over HTTP, which still works on current bridges and needs no certificate handling. Lights, motion sensors and temperature sensors.
- **Fully Kiosk:** screen on/off, screen brightness and battery. Motion isn't in its REST status, so it isn't here.
- **WLED:** on/off, brightness, and the preset list as a choice.

## Global Constraints

- Tests never touch real devices or the network (`CLAUDE.md`). Integrations are tested with fake device replies.
- Integration settings live in the database, not in `/config` files.
- Credentials are never stored in plain text, never logged, and never sent back to the browser.
- Every command goes through `can_control` (unchanged: the existing routes do this).
- No GPL library in the core. This plan adds no library.
- A device's stable identity is its MAC address or serial number, never its IP address.
- A device that stops answering reads as `unavailable` and comes back on its own.
- Each integration gets a page in `docs/integrations/`, written like `kasa.md`, linked from `docs/integrations/README.md`.
- Run from `core/`: `ruff check .`, `mypy --strict cave`, `pytest`. From `console/`: `pnpm lint`, `pnpm test`.
- Commits: Conventional Commits, `git commit -s`.

## Review Focus

1. **A device that's off or slow.** Polls mark its entities `unavailable` within one poll; a command gives `409 "This device isn't responding."`; nothing waits longer than `TIMEOUT_SECONDS`. Pinned in Task 1 and in each integration's offline test.
2. **A secret in a URL reaching a log.** The Hue key and the Fully Kiosk password are part of the request path or query. No error, log line or API answer may contain them. Pinned in Tasks 1, 4 and 5 by asserting the secret's text is absent from `caplog.text`.
3. **A reply that isn't what CAVE expects:** an HTML login page, broken JSON, a missing key. It reads as unavailable, never as a crash or a wrong state. Pinned in Tasks 1 and 3.
4. **The host key was replaced, so a saved key can't be read.** `credentials.get` returns `None`; the device's entities read `unavailable`, and the log says to remove and add it again. Pinned in Tasks 4 and 5.
5. **The device changes behind CAVE's back:** a light added to or removed from a Hue bridge, a WLED preset renamed. New ones appear on the next poll; missing ones read `unavailable` rather than vanishing from dashboards. Pinned in Tasks 2 and 4.

---

### Task 1: The device HTTP client, light commands, and registering integrations

**Files:**
- Create: `core/cave/integrations/http.py`
- Modify: `core/cave/controls.py` (add a `light` table)
- Modify: `core/cave/api/app.py` (register the integrations this plan adds; empty list for now)
- Create: `core/tests/fake_http.py`
- Test: `core/tests/test_device_http.py`, `core/tests/test_controls.py`

**Interfaces:**
- Produces, in `cave/integrations/http.py`:

```python
TIMEOUT_SECONDS = 5.0
MAX_BYTES = 1_000_000
NOT_RESPONDING = "This device isn't responding."

class DeviceError(Exception): ...  # message never contains the path, query or body

Fetch = Callable[..., Awaitable[Any]]

async def request(method: str, host: str, path: str, *, port: int = 80, body: Any = None) -> Any: ...
    # JSON-encodes body when given; returns the parsed JSON reply.
    # DeviceError("no answer") on connect failure or timeout, ("HTTP <status>") on status >= 400,
    # ("not JSON") on a reply that doesn't parse, ("too large") past MAX_BYTES.
```

- Produces, in `tests/fake_http.py`: `FakeHttp(routes: dict[tuple[str, str], Any])`, an async callable with the same signature as `request`. A route value is a reply, or a callable `(body) -> reply`. `offline = True` makes every call raise `DeviceError("no answer")`. It records `calls: list[tuple[str, str, str, Any]]` as `(method, host, path, body)`. A path not in `routes` raises `DeviceError("HTTP 404")`.
- Produces, in `cave/controls.py`: capability `light` with `turn_on` (optional `brightness`: a number, rounded to an int, 0–255), `turn_off` and `toggle` (no args).
- Produces, in `cave/api/app.py`: a module-level `INTEGRATIONS: list[Callable[[StateMachine, Credentials], Integration]] = []` that `create_app` walks, calling `app.state.integrations.register(make(app.state.states, app.state.credentials))`. Tasks 2–5 each append their class.

- [ ] **Step 1: Write the failing tests**
  - `test_device_http.py`, against a real `http.server` on `127.0.0.1` in a thread (the test's own loopback server, not the network):
    - `test_get_and_post_json`: GET returns the parsed reply; POST sends the JSON body and returns the reply.
    - `test_errors_never_show_the_path`: a 500 reply to `/api/s3cr3t-key/lights?password=hunter2` raises `DeviceError("HTTP 500")`, and neither `s3cr3t-key` nor `hunter2` appears in `str(e)` or `caplog.text`.
    - `test_not_json_and_too_large`: an HTML body raises `DeviceError("not JSON")`; a body past `MAX_BYTES` (monkeypatched to 100) raises `DeviceError("too large")`.
    - `test_timeout`: with `TIMEOUT_SECONDS` monkeypatched to 0.2 and a handler that sleeps 1 s, the call raises `DeviceError("no answer")` in under 1 s.
  - `test_controls.py`:
    - `test_light_brightness`: `check_command("light", "turn_on", {"brightness": 127.6}, {})` gives `{"brightness": 128}`; `{"brightness": 300}` raises `ValueError` containing `"0 to 255"`; `turn_on` with no args gives `{}`; `"turn_off"` and `"toggle"` give `{}`; `"blink"` raises `ValueError`.

- [ ] **Step 2: Run and see them fail**

Run: `pytest tests/test_device_http.py tests/test_controls.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cave.integrations.http'`, and the light test failing.

- [ ] **Step 3: Implement** `http.py` with `http.client.HTTPConnection(host, port, timeout=TIMEOUT_SECONDS)` inside `asyncio.to_thread`, reading at most `MAX_BYTES + 1`. Add the `light` table to `controls.py`. Add `INTEGRATIONS` and the loop to `app.py`, after `app.state.integrations` is created.

- [ ] **Step 4: Run the tests and the suite**

Run: `pytest tests/test_device_http.py tests/test_controls.py -v && pytest -q && ruff check . && mypy --strict cave`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add core/cave/integrations/http.py core/cave/controls.py core/cave/api/app.py core/tests/fake_http.py core/tests/test_device_http.py core/tests/test_controls.py
git commit -s -m "feat: a device HTTP client and brightness for lights"
```

### Task 2: WLED

**Files:**
- Create: `core/cave/integrations/wled/__init__.py` (empty), `core/cave/integrations/wled/service.py`
- Modify: `core/cave/api/app.py` (append `WledIntegration` to `INTEGRATIONS`)
- Create: `core/tests/fixtures/wled/info.json`, `state.json`, `presets.json` (a real WLED 0.14 reply shape: `info` with `"brand": "WLED"`, `"name"`, `"mac"`, `"arch"`; `state` with `on`, `bri`, `ps`; `presets` with `"0": {}` and two named presets)
- Create: `docs/integrations/wled.md`; modify `docs/integrations/README.md` (link it)
- Test: `core/tests/test_wled.py`

**Interfaces:**
- Consumes: `Integration`, `Device`, `Found`, `PairingError` (plan 1, `cave/integrations/base.py`); `request`, `DeviceError`, `NOT_RESPONDING` (Task 1).
- Produces: `WledIntegration(states: StateMachine, credentials: Credentials, fetch: Fetch = request)` with `domain = "wled"`, `title = "WLED"`, `pairing = "none"`, `pairing_hint = ""`, `POLL_SECONDS = 15.0`.
  - `probe`: `GET /json/info`; a reply whose `brand` is `"WLED"` gives `Found(mac, host, info["arch"], info["name"])`; anything else gives `None`.
  - `pair(host, None)`: the same check, returning `(found, {})`.
  - Entities for a device with MAC `m`: `light.wled_<m>` (state `on`/`off`, attribute `brightness` 0–255) and `select.wled_<m>_preset` (attribute `options`: preset names in id order, skipping id `0`; state the active preset's name, or `""`).
  - Commands: `turn_on`/`turn_off`/`toggle` and `turn_on {brightness}` post `{"on": …, "bri": …}` to `/json/state`; `select_option {option}` posts `{"ps": <id>}`.
  - `attach` registers both entities and their handlers (no network); the first poll fills their state. `detach` removes them.

- [ ] **Step 1: Write the failing tests** in `core/tests/test_wled.py`, with `FakeHttp` serving the fixtures:
  - `test_probe_recognises_wled_only`: the fixture gives `Found("aabbccddeeff", "192.168.1.50", "esp32", "Desk strip")`; a reply without `"brand": "WLED"` gives `None`.
  - `test_poll_sets_light_and_preset`: after `attach` and one `poll()`, the light is `on` with `brightness: 128`, and the preset entity's state is the active preset's name with `options` in id order.
  - `test_commands_post_state`: `turn_on {brightness: 200}` posts `{"on": true, "bri": 200}`; `select_option {"option": "Sunset"}` posts `{"ps": 2}`; an option not in `options` is refused by `check_command` before any post.
  - `test_offline_reads_unavailable_and_commands_say_so`: with `fake.offline = True`, `poll()` sets both entities to `unavailable`, and a command raises `ValueError(NOT_RESPONDING)`.
  - `test_renamed_preset_shows_on_next_poll`: change the fake's presets reply and poll again; `options` follows.
  - `test_detach_removes_entities`.

- [ ] **Step 2: Run and see them fail**

Run: `pytest tests/test_wled.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cave.integrations.wled'`.

- [ ] **Step 3: Implement `WledIntegration`** and append it to `INTEGRATIONS`. `run()` polls every device every `POLL_SECONDS`, catching each device's `DeviceError` so one device never stops the others. Write `docs/integrations/wled.md` (how to add, what CAVE stores: nothing secret, what works, if it says not responding) and link it from the README.

- [ ] **Step 4: Run the tests and the suite**

Run: `pytest tests/test_wled.py -v && pytest -q && ruff check . && mypy --strict cave`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add core/cave/integrations/wled core/cave/api/app.py core/tests/fixtures/wled core/tests/test_wled.py docs/integrations/wled.md docs/integrations/README.md
git commit -s -m "feat(integrations): WLED lights and presets"
```

### Task 3: Shelly

**Files:**
- Create: `core/cave/integrations/shelly/__init__.py` (empty), `core/cave/integrations/shelly/service.py`
- Modify: `core/cave/api/app.py` (append `ShellyIntegration`)
- Create: `core/tests/fixtures/shelly/gen1_shelly.json`, `gen1_status.json` (Shelly 1PM: `relays[0].ison`, `meters[0].power`, `meters[0].total` in watt-minutes), `gen2_shelly.json`, `gen2_status.json` (Shelly Plus 2PM: `"gen": 2`, `switch:0` and `switch:1` with `output`, `apower`, `aenergy.total` in Wh)
- Create: `docs/integrations/shelly.md`; modify `docs/integrations/README.md`
- Test: `core/tests/test_shelly.py`

**Interfaces:**
- Consumes: as Task 2.
- Produces: `ShellyIntegration(states, credentials, fetch=request)` with `domain = "shelly"`, `title = "Shelly"`, `pairing = "none"`, `pairing_hint = ""`, `POLL_SECONDS = 15.0`.
  - `probe`: `GET /shelly`. Gen 2+ is a reply with `gen >= 2` (id from `mac`, model from `model`, name from `name` or the model). Gen 1 is a reply with `type` and `mac` (model from `type`). Anything else is `None`.
  - `pair`: probes, then refuses with `PairingError("This Shelly has a password set. CAVE can't use password-protected Shelly devices yet.")` when `auth_en` (gen 2) or `auth` (gen 1) is true, and with `PairingError("CAVE supports Shelly relays for now, not dimmers or colour lights.")` when the status has no relay or switch channel. Returns `(found, {})`. The device's `settings` keep `{"gen": 1 | 2, "channels": n}`.
  - Entities per channel `n` for MAC `m`: `switch.shelly_<m>_<n>`; `sensor.shelly_<m>_<n>_power` (attribute `unit: "W"`) and `sensor.shelly_<m>_<n>_energy` (attribute `unit: "kWh"`, from watt-minutes ÷ 60 000 for gen 1 and Wh ÷ 1 000 for gen 2, rounded to 3 places), only where the status reports them.
  - Commands: gen 1 `GET /relay/<n>?turn=on|off|toggle`; gen 2 `GET /rpc/Switch.Set?id=<n>&on=true|false`, or `GET /rpc/Switch.Toggle?id=<n>`.

- [ ] **Step 1: Write the failing tests** in `core/tests/test_shelly.py`:
  - `test_probe_both_generations`: each fixture gives its `Found`; a non-Shelly reply gives `None`.
  - `test_pair_refuses_password_and_dimmers`: each case raises `PairingError` with its exact message.
  - `test_gen1_poll_and_command`: one relay `on`, power `12.5 W`, energy converted to kWh; `turn_off` calls `/relay/0?turn=off`.
  - `test_gen2_two_channels`: two switches and their sensors from one status call; `toggle` on channel 1 calls `/rpc/Switch.Toggle?id=1`.
  - `test_unexpected_reply_reads_unavailable`: a status reply missing `switch:0` sets that channel's entities `unavailable` and doesn't raise.
  - `test_offline_reads_unavailable_and_commands_say_so`.

- [ ] **Step 2: Run and see them fail**

Run: `pytest tests/test_shelly.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cave.integrations.shelly'`.

- [ ] **Step 3: Implement `ShellyIntegration`**, append it, and write `docs/integrations/shelly.md` (including the two refusals and what to do about them).

- [ ] **Step 4: Run the tests and the suite**

Run: `pytest tests/test_shelly.py -v && pytest -q && ruff check . && mypy --strict cave`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add core/cave/integrations/shelly core/cave/api/app.py core/tests/fixtures/shelly core/tests/test_shelly.py docs/integrations/shelly.md docs/integrations/README.md
git commit -s -m "feat(integrations): Shelly relays with power and energy"
```

### Task 4: Philips Hue

**Files:**
- Create: `core/cave/integrations/hue/__init__.py` (empty), `core/cave/integrations/hue/service.py`
- Modify: `core/cave/api/app.py` (append `HueIntegration`)
- Create: `core/tests/fixtures/hue/config.json` (unauthenticated `/api/config`: `bridgeid`, `name`, `modelid`, `mac`), `lights.json` (two lights; one `reachable: false`), `sensors.json` (one `ZLLPresence`, one `ZLLTemperature` in hundredths of °C, one `Daylight` to ignore)
- Create: `docs/integrations/hue.md`; modify `docs/integrations/README.md`
- Test: `core/tests/test_hue.py`

**Interfaces:**
- Consumes: as Task 2, plus `Credentials.get` (plan 1).
- Produces: `HueIntegration(states, credentials, fetch=request)` with `domain = "hue"`, `title = "Philips Hue"`, `pairing = "button"`, `pairing_hint = "Press the round button on top of the Hue bridge, then choose Add within 30 seconds."`, `POLL_SECONDS = 15.0`.
  - `probe`: `GET /api/config`; a reply with `bridgeid` gives `Found(bridgeid.lower(), host, modelid, name)`.
  - `pair(host, None)`: `POST /api` with `{"devicetype": "cave#hub"}`. A reply with `error.type == 101` raises `PairingError("Press the button on the Hue bridge first, then choose Add again.")`; `success.username` is returned as `{"key": username}`.
  - The key is read back as `credentials.get("hue", f"{device_id}:key")`. When it is `None`, every entity of that bridge reads `unavailable` and one warning is logged per poll naming the bridge id and saying to remove and add it again. The key itself is never logged.
  - Entities for bridge `b`, light or sensor number `n`: `light.hue_<b>_<n>` (attribute `brightness` 0–255, from Hue's 1–254); `binary_sensor.hue_<b>_<n>_motion`; `sensor.hue_<b>_<n>_temperature` (attribute `unit: "°C"`, one decimal place). A light with `reachable: false` reads `unavailable`.
  - `attach` registers nothing, because only the bridge knows its lights; `run()` polls once at start, so they appear within seconds of CAVE starting or the bridge being added.
  - Each poll reads `/api/<key>/lights` and `/api/<key>/sensors`, registers any new light or sensor, and sets ones that disappeared to `unavailable` (they stay registered until the bridge is removed).
  - Commands: `PUT /api/<key>/lights/<n>/state` with `{"on": …}` and, for `brightness`, `"bri"` scaled to 1–254. `toggle` reads the current state, like Kasa.

- [ ] **Step 1: Write the failing tests** in `core/tests/test_hue.py`:
  - `test_probe_and_pair`: `probe` gives the bridge; `pair` with the 101 reply raises the exact `PairingError`; with the success reply returns `{"key": "…"}`.
  - `test_poll_lights_and_sensors`: light 1 `on` with brightness scaled, light 2 `unavailable`, motion `on`, temperature `21.5`, and nothing made for `Daylight`.
  - `test_new_and_missing_lights_follow_the_bridge`: add light 3 to the fake's reply and poll: it's registered. Remove light 1 and poll: it reads `unavailable` and is still registered.
  - `test_brightness_command_scales`: `turn_on {brightness: 255}` puts `{"on": true, "bri": 254}`.
  - `test_unreadable_key_reads_unavailable`: store the key with one host key, then build `Credentials` with another. After a poll, every entity is `unavailable`, no request was made, and the log names the bridge but contains no key.
  - `test_key_never_logged`: with the fake returning HTTP 500 for every path, poll; the key's text is absent from `caplog.text`.

- [ ] **Step 2: Run and see them fail**

Run: `pytest tests/test_hue.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cave.integrations.hue'`.

- [ ] **Step 3: Implement `HueIntegration`**, append it, and write `docs/integrations/hue.md` (the button step, what CAVE stores: the bridge key, encrypted).

- [ ] **Step 4: Run the tests and the suite**

Run: `pytest tests/test_hue.py -v && pytest -q && ruff check . && mypy --strict cave`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add core/cave/integrations/hue core/cave/api/app.py core/tests/fixtures/hue core/tests/test_hue.py docs/integrations/hue.md docs/integrations/README.md
git commit -s -m "feat(integrations): Philips Hue lights and sensors"
```

### Task 5: Fully Kiosk Browser

**Files:**
- Create: `core/cave/integrations/fully/__init__.py` (empty), `core/cave/integrations/fully/service.py`
- Modify: `core/cave/api/app.py` (append `FullyKioskIntegration`)
- Create: `core/tests/fixtures/fully/device_info.json` (`deviceID`, `deviceName`, `deviceModel`, `screenOn`, `screenBrightness` 0–255, `batteryLevel`), `login_needed.json` (`{"status": "Error", "statustext": "Please login"}`)
- Create: `docs/integrations/fully-kiosk.md`; modify `docs/integrations/README.md`
- Test: `core/tests/test_fully.py`

**Interfaces:**
- Consumes: as Task 4.
- Produces: `FullyKioskIntegration(states, credentials, fetch=request)` with `domain = "fully"`, `title = "Fully Kiosk Browser"`, `pairing = "password"`, `pairing_hint = "The Remote Administration password set in Fully Kiosk's settings."`, `PORT = 2323`, `POLL_SECONDS = 15.0`.
  - `probe`: `GET /?cmd=deviceInfo&type=json` on port 2323 without a password. The login reply gives `Found("", host, "Fully Kiosk Browser", "Fully Kiosk Browser")`: the id is only known after pairing, so `added` reads false until then. A full reply (no password set) gives the real `Found`. Anything else gives `None`.
  - `pair(host, password)`: `GET /?cmd=deviceInfo&type=json&password=<url-encoded>`. The login reply raises `PairingError("That password didn't work. Check Remote Administration in Fully Kiosk's settings.")`. A full reply returns `(Found(<id>, host, deviceModel, deviceName), {"password": password})`, where `<id>` is `deviceID` lowercased with everything except `a–z` and `0–9` removed. An empty `<id>` raises `PairingError("This tablet didn't report an id CAVE can use.")`.
  - Entities for id `d`: `switch.fully_<d>_screen`; `number.fully_<d>_brightness` (attributes `min: 0`, `max: 255`, `step: 1`); `sensor.fully_<d>_battery` (attribute `unit: "%"`).
  - Commands: `cmd=screenOn` / `cmd=screenOff`; brightness `cmd=setStringSetting&key=screenBrightness&value=<n>`; always with the password.
  - An unreadable password behaves like Hue's unreadable key (Task 4).

- [ ] **Step 1: Write the failing tests** in `core/tests/test_fully.py`:
  - `test_probe_sees_fully_before_the_password`: the login reply gives a `Found` with id `""`; an unrelated reply gives `None`.
  - `test_pair_checks_the_password`: a wrong password raises the exact `PairingError`; a right one returns the cleaned id and `{"password": …}`.
  - `test_poll_and_commands`: screen `on`, brightness `120`, battery `87`; `set_value {value: 200}` sends the brightness command; `turn_off` sends `screenOff`.
  - `test_password_never_logged`: with the fake offline, poll and send a command; the password's text is absent from `caplog.text` and from the `ValueError`.
  - `test_unreadable_password_reads_unavailable`.

- [ ] **Step 2: Run and see them fail**

Run: `pytest tests/test_fully.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cave.integrations.fully'`.

- [ ] **Step 3: Implement `FullyKioskIntegration`**, append it, and write `docs/integrations/fully-kiosk.md` (turning on Remote Administration, that the password goes over plain HTTP on the home network because that is the app's API, and that CAVE stores it encrypted).

- [ ] **Step 4: Run the tests and the suite**

Run: `pytest tests/test_fully.py -v && pytest -q && ruff check . && mypy --strict cave`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add core/cave/integrations/fully core/cave/api/app.py core/tests/fixtures/fully core/tests/test_fully.py docs/integrations/fully-kiosk.md docs/integrations/README.md
git commit -s -m "feat(integrations): Fully Kiosk Browser tablets"
```

### Task 6: A brightness slider on light tiles

**Files:**
- Modify: `console/src/cards/controls.tsx` (a `light` branch)
- Modify: `console/src/cards/Tile.tsx` (a light with a `brightness` attribute keeps its toggle and shows the slider under it)
- Test: `console/src/cards/controls.test.tsx`

**Interfaces:**
- Consumes: the light convention from Task 1 (`brightness` 0–255; `turn_on {brightness}`); the existing `Level` slider in `controls.tsx`.
- Produces: light tiles show `Level` labelled `"Brightness"`, from 0 to 100 with unit `"%"`, starting at `round(brightness × 100 ÷ 255)`. Letting go sends `turn_on {brightness: round(percent × 255 ÷ 100)}`. A light without a numeric `brightness` attribute (a Kasa-style on/off light) shows no slider.

- [ ] **Step 1: Write the failing tests** in `console/src/cards/controls.test.tsx`:
  - `"light tiles get a brightness slider"`: a light at `brightness: 128` shows a slider named "Brightness" at 50, and the tile's toggle is still a button named after the light.
  - `"moving it sends brightness on 0-255"`: moving to 100 and letting go posts `/entities/light.desk/commands/turn_on` with `{ brightness: 255 }`.
  - `"no slider without brightness"`: a light with no `brightness` attribute shows no slider.

- [ ] **Step 2: Run and see them fail**

Run: `pnpm test -- controls`
Expected: the three new tests fail; the existing tests pass.

- [ ] **Step 3: Implement** the `light` branch in `Controls`, and in `Tile` render the toggle button and, beneath it, `<Controls>` for a light with a numeric `brightness`.

- [ ] **Step 4: Run the tests and lint**

Run: `pnpm test && pnpm lint`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add console/src/cards/controls.tsx console/src/cards/Tile.tsx console/src/cards/controls.test.tsx
git commit -s -m "feat(console): a brightness slider on light tiles"
```
