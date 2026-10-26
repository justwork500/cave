# CAVE Phase 1 · Plan 2: Screens, networks and HTTPS — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A wall tablet can be enrolled as a screen, with a key it can't export, approved by an Admin, and signed in by challenge. It is limited to the local network, which Admins manage in the database, and CAVE serves only HTTPS, on a self-signed certificate it makes on first run. Before any of this ships, the tablet browser spike shows which browsers actually allow it.

**Architecture:** Plan 1's core gains a `screens` module (enrollment codes, public keys, single-use challenges, screen sessions) that produces a `Principal(kind="screen")`, so `cave.access.evaluate` needs no changes. Network settings move from `Settings` into the database behind `cave.access.netconfig`. A `cave serve` entry point runs uvicorn with TLS only. One small browser script, `screen.js`, holds the WebCrypto code. Both the spike page and the real enrollment page use it.

**Tech Stack:** Python 3.13, FastAPI, `cryptography` (new: X.509 certificate generation and ECDSA P-256 verification, which the standard library can't do), uvicorn with TLS; plain browser JavaScript (WebCrypto, IndexedDB), with no build step.

**Spec:** `docs/superpowers/specs/2026-10-25-cave-phase1-design.md` (sections "Screens (device assignments)", "Network condition", "HTTPS"). This builds on Plan 1, now on `main`.

## Global Constraints

- Everything in Plan 1's Global Constraints still holds.
- Screen key: **ECDSA P-256** made with WebCrypto, `extractable: false`, kept in IndexedDB. CAVE stores only the public key (SPKI DER) and its **SHA-256 fingerprint**. No MAC addresses or serial numbers.
- Enrollment link and QR code: one-time, **expires after 10 minutes**.
- A new screen is **Pending** until an Admin approves it. Approve, enroll and revoke are all audited.
- Screen sign-in: a random **single-use** challenge, signed by the tablet and verified against the stored public key. This happens on every connect and **at least every 12 hours**.
- Screens never see the admin console. Revoking a screen deletes its public key and ends its sessions at once.
- Local ranges are pre-filled from CAVE's own interfaces. VPN ranges are added by hand. **Trusted proxies:** with none listed, forwarded headers are ignored.
- **HTTPS only.** CAVE makes a self-signed certificate on first run and shows its fingerprint in the console. The user's own certificate is supported. **No local certificate authority. No plain HTTP.**
- WebCrypto ECDSA signatures are **IEEE P1363** (raw `r‖s`, 64 bytes for P-256), not DER. The server converts before verifying.

## Review Focus

1. **A signature replayed from an earlier challenge** → refused, because each challenge is consumed on first use, success or failure. Pinned in Task 5.
2. **A challenge issued for screen A but signed by screen B's key** (or the reverse) → refused, because the signed message names the screen ID. Pinned in Task 5.
3. **Enrollment code used twice, or after 10 minutes** → the second use and the late use are refused, and the screen stays without a key. Pinned in Task 4.
4. **An invalid CIDR typed into Networks** → rejected with a 422 that names the bad entry, never stored, so requests can't start failing with 500s. Pinned in Task 3 (this is Plan 1's deferred minor 13).
5. **A screen revoked while its WebSocket is open** → the socket closes with 4401 at once. Pinned in Task 6.

---

## File structure

```text
core/cave/migrations/0001_initial.sql      # moved from cave/schema.sql, unchanged
core/cave/migrations/0002_screens_network.sql
core/cave/db.py                            # ordered migrations
core/cave/tls.py                           # self-signed cert creation, fingerprint
core/cave/__main__.py                      # `python -m cave serve`
core/cave/access/netconfig.py              # local ranges + trusted proxies in the DB
core/cave/auth/screens.py                  # enrollment, approval, challenges, screen sessions
core/cave/api/screens.py                   # screen admin + enroll + challenge routes
core/cave/api/system.py                    # Networks + Certificate routes
core/cave/web/screen.js                    # WebCrypto key + signing, shared
core/cave/web/spike.html                   # tablet browser spike page
core/cave/web/enroll.html                  # real enrollment page
docs/install/tablets.md                    # spike results + how to enroll a tablet
```

---

### Task 1: Ordered migrations and the TLS certificate

**Files:**
- Move: `core/cave/schema.sql` → `core/cave/migrations/0001_initial.sql` (content unchanged)
- Modify: `core/cave/db.py`, `core/pyproject.toml` (add `cryptography>=43`; package data `migrations/*.sql`, `web/*`)
- Create: `core/cave/tls.py`
- Test: `core/tests/test_db.py` (extend), `core/tests/test_tls.py`

**Interfaces:**
- Produces: `Database._migrate()` applies every `migrations/NNNN_*.sql` whose number is greater than `PRAGMA user_version`, in order, each in one transaction, and sets `user_version` to that number. `SCHEMA_VERSION` is removed; the latest version is the highest file number.
- Produces: `tls.ensure_certificate(directory: Path, hostnames: list[str], ips: list[str]) -> tuple[Path, Path]`. It returns `(cert.pem, key.pem)` and creates them only if missing. The key is ECDSA P-256 (key file `0600` where the OS supports it). The certificate is self-signed for 825 days, with SANs for every hostname and IP. `tls.fingerprint(cert_path: Path) -> str` returns the SHA-256 of the DER certificate as uppercase hex pairs joined by `:`.

- [ ] **Step 1: Write failing tests**
  - `test_db.py::test_migrations_apply_in_order` (in this task a fresh DB has `user_version == 1`; Task 3 raises it to 2)
  - `test_db.py::test_existing_v1_db_is_upgraded_not_recreated` (insert a user at v1, reopen, and the user still exists)
  - `test_tls.py::test_creates_once_and_reuses` (the second call returns the same files with unchanged mtime)
  - `test_tls.py::test_sans_include_hostnames_and_ips` (parse with `cryptography.x509`: DNS `cave.local`, IP `192.168.1.10`)
  - `test_tls.py::test_fingerprint_format` (matches `^([0-9A-F]{2}:){31}[0-9A-F]{2}$` and equals `hashlib.sha256(der).hexdigest()`, upper-cased and colon-joined)
- [ ] **Step 2:** Run `cd core && ../.venv/Scripts/python -m pytest -q tests/test_db.py tests/test_tls.py`. Expected: FAIL.
- [ ] **Step 3:** Implement the changes. Install `cryptography` into the venv.
- [ ] **Step 4:** Rerun, then the full suite with `-W error`, `ruff check .` and `mypy --strict cave`. Expected: all PASS.
- [ ] **Step 5: Commit** `git commit -s -m "feat(core): ordered migrations and self-signed TLS certificate"`

---

### Task 2: The tablet browser spike

The spec's "must verify early" item. It decides one line of the install docs, not the code, so the later tasks don't wait for its answer.

**Files:**
- Create: `core/cave/web/screen.js`, `core/cave/web/spike.html`, `core/cave/__main__.py`
- Modify: `core/cave/api/app.py` (serve `GET /spike` and `GET /static/screen.js` from `cave/web`)
- Test: `core/tests/test_serve.py`

**Interfaces:**
- Produces in `screen.js`, as an ES module, with no dependencies:
  - `async function getOrCreateKey(): Promise<CryptoKeyPair>` — loads from IndexedDB database `cave`, store `keys`, key `screen`. Otherwise it generates `{name: "ECDSA", namedCurve: "P-256"}` with `extractable: false` and usages `["sign", "verify"]`, then stores it.
  - `async function publicKeySpki(pair): Promise<string>` — base64 of `exportKey("spki", pair.publicKey)`. A public key is always exportable.
  - `async function signChallenge(pair, screenId: string, nonce: string): Promise<string>` — base64 of `sign({name: "ECDSA", hash: "SHA-256"}, privateKey, utf8("cave-screen-auth:" + screenId + ":" + nonce))`.
  - `async function probe(): Promise<Record<string, boolean | string>>` — used only by the spike. It reports `isSecureContext`, `crypto.subtle` present, key generated, key stored, key reloaded after a page reload (via a `sessionStorage` flag), `extractable === false`, private-key export refused, signature made, and `navigator.userAgent`.
- Produces: `spike.html` runs `probe()`, shows each result as a pass or fail row in large type, and has a "Reload and check again" button.
- Produces: `python -m cave serve [--host 0.0.0.0] [--port 8443] [--data ./data] [--cert PATH --key PATH]`. It calls `tls.ensure_certificate(data/"tls", [socket.gethostname(), "localhost"], <host IPv4 addresses>)` unless `--cert`/`--key` are given, prints the URL and the certificate fingerprint, and runs uvicorn with `ssl_certfile`/`ssl_keyfile`. There is no HTTP listener.

- [ ] **Step 1: Write failing tests:** `test_serve.py::test_spike_page_served` (`GET /spike` → 200 and `text/html`, containing `screen.js`) and `test_serve.py::test_screen_js_served` (`GET /static/screen.js` → 200, `javascript` content type, contains `extractable` and `cave-screen-auth:`).
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement. Get the host's IPv4 address the standard-library way (a UDP `connect` to a TEST-NET address, no packets sent), plus `127.0.0.1`. Use `shortcut:` comment form for the limit (one interface only).
- [ ] **Step 4:** Rerun, then the full suite. Expected: PASS.
- [ ] **Step 5: Smoke test in the browser pane.** Start `python -m cave serve --port 8443 --data <scratchpad>/spike-data` in the background and open `https://localhost:8443/spike` in the built-in browser pane. Expected: every row passes. Localhost counts as a secure context, so this checks the script itself, not the self-signed certificate case.
- [ ] **Step 6: Commit** `git commit -s -m "feat(web): screen key script and tablet browser spike page"`
- [ ] **Step 7: Hand the spike to the user (the one human step in this plan).** Tell them, in one message, to open `https://<host-ip>:8443/spike` on each tablet they have (iPad Safari, an Android Chrome tablet, a Fire tablet), accept the certificate warning once, and read out or screenshot the rows. Keep going with Task 3 without waiting. Task 7 writes their answers into the docs.

---

### Task 3: Networks in the database

**Files:**
- Create: `core/cave/migrations/0002_screens_network.sql` (all of this plan's tables), `core/cave/access/netconfig.py`, `core/cave/api/system.py`
- Modify: `core/cave/settings.py` (`local_ranges` and `trusted_proxies` become **first-run seeds only**), `core/cave/api/deps.py`, `core/cave/api/entities.py`, `core/cave/api/admin.py`, `core/cave/api/ws.py`, `core/cave/api/app.py`
- Test: `core/tests/test_netconfig.py`

**Interfaces:**
- Tables in `0002`:
  - `network_ranges(cidr TEXT, kind TEXT CHECK (kind IN ('local','trusted_proxy')), PRIMARY KEY (cidr, kind))`
  - `screens(id TEXT PRIMARY KEY, name TEXT NOT NULL, status TEXT CHECK (status IN ('awaiting_key','pending','approved','revoked')), public_key TEXT, fingerprint TEXT, created_at TEXT, approved_by TEXT, approved_at TEXT)`
  - `enrollment_codes(code_hash TEXT PRIMARY KEY, screen_id TEXT REFERENCES screens(id) ON DELETE CASCADE, expires_at TEXT, used_at TEXT)`
  - `screen_challenges(nonce TEXT PRIMARY KEY, screen_id TEXT, expires_at TEXT)`
  - `screen_sessions(id TEXT PRIMARY KEY, screen_id TEXT REFERENCES screens(id) ON DELETE CASCADE, created_at TEXT)`
- Produces in `netconfig.py`:
  - `@dataclass(frozen=True) class NetConfig: local_ranges: tuple[str, ...]; trusted_proxies: tuple[str, ...]`
  - `load(db) -> NetConfig`
  - `class InvalidRange(ValueError)` with `.value: str`
  - `save(db, actor: str, local_ranges: list[str], trusted_proxies: list[str]) -> NetConfig` — each entry is normalized with `ip_network(v, strict=False)`. An invalid entry raises `InvalidRange` and nothing is stored. The change is audited as `network.update` with old and new values.
  - `seed(db, settings: Settings) -> None` — runs only when `network_ranges` is empty. It uses the `Settings` lists if given, otherwise `detect_local_ranges()`.
  - `detect_local_ranges() -> list[str]` — the `/24` around the host's private IPv4 address (the same UDP trick as Task 2), with a `shortcut:` comment (one interface; the user adds others).
- Produces in `deps.py`: `net(request: HTTPConnection) -> NetConfig`. Every place that read `get_settings(request).local_ranges` or `.trusted_proxies` now reads `net(request)` instead; find them with `grep -rn "local_ranges\|trusted_proxies" cave`. Each request uses one `NetConfig`. Also fix Plan 1's deferred minor 7 here: `client_ip` joins `request.headers.getlist("x-forwarded-for")` with `,`.
- Produces in `system.py` (manage `section:system`):
  - `GET /api/v1/system/networks` → `{"local_ranges": [...], "trusted_proxies": [...]}`
  - `PUT /api/v1/system/networks` (same body) → saved values, or `422 {"detail": "Not a valid address range: <value>"}`. Publishes `access_changed`.
  - `GET /api/v1/system/certificate` → `{"fingerprint", "not_after", "self_signed": bool}`, read from the cert file `cave serve` recorded in `app.state.cert_path` (or 404 when none, as in tests).

- [ ] **Step 1: Write failing tests:**
  - `test_save_normalizes_and_audits` (`"192.168.1.7/24"` is stored as `"192.168.1.0/24"`)
  - `test_invalid_range_rejected_and_nothing_stored` (Review Focus 4: `PUT` with `["10.0.0.0/8", "nope"]` → 422 naming `nope`; `GET` unchanged)
  - `test_seed_runs_once` (an Admin's later change survives a restart)
  - `test_operator_cannot_change_networks` (403)
  - `test_networks_change_applies_immediately` (sam's command on a `local` item from `10.9.9.9` → 403; after the Admin adds `10.9.9.0/24` → 202)
  - `test_xff_multiple_header_lines_joined` (two `X-Forwarded-For` lines through a trusted proxy resolve to the rightmost untrusted address across both)
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement. Change Task 1's `test_migrations_apply_in_order` to expect `user_version == 2`. Update `tests/conftest.py`'s `app` fixture so `Settings(local_ranges=["192.168.1.0/24"])` still seeds the DB, so the Plan 1 tests keep passing unchanged.
- [ ] **Step 4:** Rerun, then the full suite. Expected: PASS, with every Plan 1 test still green.
- [ ] **Step 5: Commit** `git commit -s -m "feat(system): networks and trusted proxies stored and validated in the database"`

---

### Task 4: Screen enrollment and approval

**Files:**
- Create: `core/cave/auth/screens.py`, `core/cave/api/screens.py`, `core/cave/web/enroll.html`
- Modify: `core/cave/api/app.py`
- Test: `core/tests/test_screens.py`; the helper `tests/screen_key.py` emulates a tablet with `cryptography` (P-256 key, SPKI base64, P1363 signatures)

**Interfaces:**
- Produces in `screens.py`:
  - `@dataclass(frozen=True) class Screen: id: str; name: str; status: Literal["awaiting_key", "pending", "approved", "revoked"]; fingerprint: str | None; created_at: datetime`
  - `create(db, actor: str, name: str, now: datetime, screen_id: str | None = None) -> tuple[Screen, str]` — the screen in `awaiting_key` (ID is `uuid4().hex` unless given), plus a one-time code (`secrets.token_urlsafe(32)`, stored as SHA-256, valid for 10 minutes).
  - `class EnrollError(Exception)` with `.message`.
  - `enroll(db, code: str, public_key_spki_b64: str, now: datetime) -> Screen` — refuses an unknown, used or expired code with `EnrollError("This enrollment link has expired. Ask an Admin for a new one.")`. Refuses a public key that isn't P-256 SPKI with `EnrollError("This browser's key isn't supported.")`. Marks the code used, stores the key and its fingerprint (SHA-256 of the SPKI DER, in the Task 1 format), sets `pending`, and audits `screen.enroll` with actor `screen:<id>`.
  - `approve(db, actor, screen_id) -> Screen` — only from `pending`.
  - `revoke(db, actor, screen_id) -> Screen` — any status. It clears `public_key`, deletes `screen_sessions`, sets `revoked`, and publishes nothing itself (the route does).
  - `list_screens(db) -> list[Screen]`, `get_screen(db, screen_id) -> Screen | None`.
- Produces in `api/screens.py`:
  - Admin routes (manage `section:users`): `POST /api/v1/screens {name}` → `201 {"screen": {...}, "enroll_url": "https://<host>/enroll#<code>", "expires_at"}`; `GET /api/v1/screens`; `POST /api/v1/screens/{id}/approve`; `POST /api/v1/screens/{id}/revoke`. The last two publish `access_changed`, and revoke also publishes `{"type": "screen_revoked", "screen_id"}`.
  - Unauthenticated route: `POST /api/v1/enroll {code, public_key}` → `200 {"screen_id", "fingerprint", "status": "pending"}`, or `400 {"detail": <EnrollError.message>}`.
- Produces: `GET /enroll` serves `enroll.html`. It reads the code from the URL fragment (fragments never reach server logs), calls `getOrCreateKey` and `publicKeySpki`, posts to `/api/v1/enroll`, and shows "Waiting for an Admin to approve this screen" with the fingerprint. It keeps `screen_id` in `localStorage`.
- The QR code is left to the console plan (Plan 6). Here the link is enough.

- [ ] **Step 1: Write failing tests:**
  - `test_enroll_then_pending_then_approved` (audit holds `screen.create`, `screen.enroll`, `screen.approve`)
  - `test_code_single_use` (Review Focus 3)
  - `test_code_expires_after_10_minutes` (Review Focus 3; `now = created + 10 min + 1 s`)
  - `test_rejects_non_p256_key` (an RSA or P-384 SPKI → 400)
  - `test_fingerprint_matches_spki_sha256`
  - `test_only_admin_creates_screens` (operator → 403)
  - `test_approve_requires_pending` (approving `awaiting_key` → 409)
  - `test_enroll_page_reads_code_from_fragment` (`GET /enroll` → 200; the HTML contains `location.hash`)
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement. Load the key with `serialization.load_der_public_key` and check `isinstance(key, ec.EllipticCurvePublicKey) and key.curve.name == "secp256r1"`.
- [ ] **Step 4:** Rerun, then the full suite. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "feat(screens): enrollment with one-time codes and admin approval"`

---

### Task 5: Screen sign-in by challenge, and screens as principals

**Files:**
- Modify: `core/cave/auth/screens.py`, `core/cave/api/screens.py`, `core/cave/api/deps.py`, `core/cave/web/enroll.html` (after approval, it signs in and redirects to `/`)
- Test: `core/tests/test_screen_auth.py`

**Interfaces:**
- Produces in `screens.py`:
  - `issue_challenge(db, screen_id: str, now: datetime) -> str` — a 32-byte `token_urlsafe` nonce, valid for 60 seconds, issued only for `approved` screens. Otherwise it raises `EnrollError("This screen isn't approved.")`.
  - `verify_challenge(db, screen_id: str, nonce: str, signature_b64: str, now: datetime) -> str` — always deletes the nonce first (Review Focus 1). It checks that the nonce belongs to this screen and isn't expired, converts the P1363 signature to DER with `utils.encode_dss_signature(int.from_bytes(r), int.from_bytes(s))`, and verifies over `b"cave-screen-auth:" + screen_id + b":" + nonce` (Review Focus 2). Then it creates a `screen_sessions` row and returns its ID. A failure raises `EnrollError("Screen sign-in failed.")`.
  - `screen_from_session(db, session_id: str, now: datetime) -> Screen | None` — `None` if the session is older than **12 hours** (absolute), or the screen isn't `approved`.
- Produces in `api/screens.py`: `POST /api/v1/screen-auth/challenge {screen_id}` → `{"nonce"}`; `POST /api/v1/screen-auth/verify {screen_id, nonce, signature}` → `204`, setting cookie `cave_screen` (Secure, HttpOnly, SameSite=Strict, `max_age` 12 h). Both are unauthenticated and both return `401` on any failure.
- Produces in `deps.py`: `screen_principal(screen: Screen) -> Principal`, i.e. `Principal(kind="screen", id=screen.id, user_id=None, role=None, group_ids=frozenset(), active=screen.status == "approved")`. `current_principal` resolves, in order: Bearer token, user session cookie, `cave_screen` cookie. `current_user` stays users-only, so `/me` and every route that needs a person still refuse screens with 401.

- [ ] **Step 1: Write failing tests:**
  - `test_screen_signs_in_and_uses_assigned_dashboard` (the garage tablet, from 192.168.1.5, opens the garage → 202)
  - `test_screen_off_network_refused` (the same tablet from 203.0.113.9 → 403)
  - `test_unenrolled_or_other_screen_refused` (a second enrolled, approved screen with no assignment → 403)
  - `test_pending_screen_cannot_get_challenge`
  - `test_replayed_signature_refused` (Review Focus 1)
  - `test_signature_for_other_screen_refused` (Review Focus 2)
  - `test_challenge_expires_after_60s`
  - `test_screen_session_expires_after_12h`
  - `test_screen_cannot_reach_admin_or_me` (`/api/v1/me` → 401, `/api/v1/users` → 401 or 403, `/api/v1/items` lists only the garage dashboard)
  - `test_revoked_screen_session_ends` (revoke, then the next command → 401)

  The garage tests reuse Plan 1's `garage` fixture: the dashboard is assigned to `("screen", "garage")`, so these tests create the screen with ID `garage` (`screens.create` accepts an optional `screen_id`, for tests and imports).
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Rerun, then the full suite. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "feat(screens): challenge sign-in and screen principals"`

---

### Task 6: Screens on the WebSocket

**Files:**
- Modify: `core/cave/api/ws.py`
- Test: `core/tests/test_ws_screens.py`

**Interfaces:**
- Consumes: `screen_from_session`, `screen_principal`, the `screen_revoked` event from Task 4.
- Produces: the handshake accepts the `cave_screen` cookie when no user session is present. `_Socket` keeps `kind` (`"user"` or `"screen"`). `still_signed_in` re-checks a screen with `screen_from_session` (so the 12-hour cap closes the socket). `refresh()` reloads a screen principal from `get_screen`. On `screen_revoked` with a matching ID, the socket closes with `4401`.

- [ ] **Step 1: Write failing tests:**
  - `test_screen_receives_only_its_entities` (the garage tablet gets `cover.garage_door` events, not `light.kids_room`)
  - `test_revoked_screen_socket_closes` (Review Focus 5)
  - `test_screen_socket_closes_after_session_cap` (monkeypatch `RECHECK_SECONDS = 0` and age the session row past 12 h, then a ping → close 4401)
  - `test_screen_ws_command_off_network_refused` (connect with `client=("203.0.113.9", …)`, send a command → `success: false`)
- [ ] **Step 2:** Run. Expected: FAIL. Socket tests that would hang while unimplemented run under `timeout 60`.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Rerun three times for flakiness, then the full suite. Expected: PASS each time.
- [ ] **Step 5: Commit** `git commit -s -m "feat(ws): screen principals on the live feed"`

---

### Task 7: Tablet docs from the spike results

**Files:**
- Create: `docs/install/tablets.md`
- Modify: `README.md` (one line linking to it)

- [ ] **Step 1:** Write `tablets.md`:
  - a results table, one row per browser the user tested: browser, OS version, each spike row, verdict
  - how to start CAVE with `python -m cave serve` until Plan 7's Compose stack exists
  - how to check the certificate fingerprint against System › Certificate before accepting the warning
  - how to add a screen, open the link on the tablet, approve it, and assign a dashboard with "Local network only"
  - a "Using your own certificate" section (`--cert`/`--key`, or a reverse proxy listed under trusted proxies)

  For any browser where the key wasn't kept or reloaded, state plainly that this browser needs your own certificate. If the user hasn't reported yet, write the table with "not yet tested" rows, and say so in the final message.
- [ ] **Step 2: Commit** `git commit -s -m "docs: enrolling wall tablets, with browser spike results"`

---

## Plan 2 done when

- CI is green: ruff, mypy --strict, pytest.
- The garage scenario passes end to end with a real (emulated) enrolled screen:
  - the enrolled tablet on the LAN is allowed
  - the same tablet off-network is refused
  - a second tablet is refused
  - a pending screen is refused
  - a revoked screen is refused, including its open socket
  - a replayed signature is refused
- `python -m cave serve` serves HTTPS only and prints the certificate fingerprint.
- `docs/install/tablets.md` records what the user's tablets did in the spike, or says plainly that they haven't been tested yet.
