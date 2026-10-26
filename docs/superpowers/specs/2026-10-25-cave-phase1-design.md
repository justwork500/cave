# CAVE Phase 1 — design

Oct 25, 2026 · Justin Coffield · Status: draft for approval

This document narrows the CAVE Design Framework (`docs/CAVE-Design-Framework.md`) to the first open-source release. Where the two disagree, this document wins for Phase 1. The framework still holds the long-term vision, the tech stack rationale and the later-phase material.

## Intent and the why

CAVE is a local-first smart-home hub that people run on their own Debian servers. The home edition is open source (Apache-2.0) and stays that way. A separate business edition (smart TVs, conference rooms, hot desks, hotel rooms) may come later; it is out of scope here, and nothing in Phase 1 should depend on it.

CAVE does not try to beat Home Assistant on device count. It beats it on **running a house well**:

1. **Access control like Entra and Intune.** Every item has one simple permission pattern, assigned to users, groups, roles and specific screens, enforced on the server.
2. **An admin console that behaves like an enterprise admin center.** List blades, object blades, wizards, audit log.
3. **Scripts as first-class citizens.** PowerShell, Python and Bash run as normal automation steps under one contract.
4. **A Test Center.** Like PowerShell's `-WhatIf`: simulate inputs to a real automation and see what it would do, without touching anything.
5. **Plain-language dashboards of standard actions.** Household members never see an entity ID.

Phase 1 proves those five things. Integrations grow in later phases.

## Goals, non-goals, anti-goals

**Goals for Phase 1**

- A person can install CAVE on Debian 13 with Docker Compose, sign in, connect MQTT devices, build an actions dashboard, assign it, and run actions, all with the internet unplugged.
- The access model below is complete and enforced server-side for the REST API, the WebSocket and every command.
- A wall tablet can be enrolled as a screen, assigned one dashboard, and limited to the local network, and that cannot be bypassed by someone who is merely on the network.
- Automations can be tested in the Test Center, whole or one step at a time, with zero side effects.
- The repository is public-ready: license, README, contributor docs, CI.

**Non-goals for Phase 1** (planned for later phases)

- Integrations other than MQTT (the list of 30 is rebuilt later; see "Later phases").
- SSO / OpenID Connect, passkeys / WebAuthn.
- Native `.deb` packages, PostgreSQL, history charts, backups UI.
- Running scripts over SSH or on the CAVE host (sandbox only).
- The visual (When / And if / Then do) automation builder. Phase 1 has the sentence builder, recipes and YAML.
- Exclude assignments, nested groups, conditions other than the network condition.
- A local certificate authority (see "HTTPS").
- The setup wizard's network scan and radio picker (no integrations to find yet).

**Anti-goals** (would make Phase 1 a failure even if it works)

- Anything that needs the internet to work. No vendor cloud, no telemetry, no hosted relay.
- Permission checks that live only in the UI. Hiding a button is cosmetic; the server decides.
- Being on the local network granting access by itself.
- Any Home Assistant code, branding or trade dress. Using open protocols that HA also uses (such as the MQTT discovery topic format) is fine.
- Business-edition concepts (multi-site, tenants, billing) leaking into the home code.

## Constraints

- Runs on Debian 13 "trixie" minimal, amd64 and arm64, installed with Docker Compose.
- Stack as decided in the framework: Python 3.13 asyncio core, FastAPI, Pydantic v2, SQLite (WAL), sandboxed Jinja2 templates; console in React 19 + TypeScript + Fluent UI React v9 + TanStack Query + Vite.
- Config as code: dashboards, automations, sequences and scripts are files under `/config`; the UI editors round-trip them.
- Apache-2.0, DCO sign-off (`git commit -s`), no CLA. Apache-2.0 lets a future business edition build on the home code.
- Visual language from the existing mockups in `design/admin-console/` (CAVE's own name and colors; no Microsoft logos or product names).

## Phase 1 scope

| Area | In Phase 1 |
| --- | --- |
| Core | Device and entity registry, areas, state machine, event bus, REST + WebSocket API, YAML config loader with JSON Schema validation |
| Sign-in | Local accounts, Argon2id passwords, TOTP (required for Admins and Operators), 10 recovery codes, lockout (5 tries → 15 min), HttpOnly SameSite=Strict session cookie, 12 h idle timeout |
| Access | Status + Visibility on every item, assignments to users / groups / roles / screens, network condition, screen enrollment, audit log (details below) |
| Console | Home, Dashboards, Devices, Automations (incl. Test Center), Scripts, Users and permissions, System (minimal) |
| Dashboards | YAML dashboards, Actions dashboard pattern; card types `tile`, `entities`, `gauge`, `button`, `markdown` |
| Automations | Triggers, conditions, actions, sequences ("Routines"), run modes, traces; sentence builder and recipes; YAML tab |
| Test Center | What-if runs of saved or draft automations with simulated inputs (details below) |
| Scripts | PowerShell 7, Python 3, Bash in the `cave-script-runner` sandbox container only, with the framework's input/output contract |
| Devices | MQTT via Mosquitto sidecar, with MQTT discovery so Zigbee2MQTT, Tasmota, Shelly and ESPHome (MQTT mode) devices appear without extra code |
| Install | `compose.yaml` with profiles `mqtt`, `scripts`; install guide for Debian 13 |
| Repo | Apache-2.0 LICENSE, README, CONTRIBUTING (DCO), CODE_OF_CONDUCT, SECURITY.md, CLAUDE.md, GitHub Actions CI |

## The access model

This replaces the framework's "5 roles + per-user toggles" grid.

### Items

An **item** is anything access applies to:

- dashboards
- console sections (Devices, Automations, Scripts, Users and permissions, System, …)
- actions: automations, sequences and scripts that can be run on demand
- features: named capabilities such as "Create API tokens" or "Use the Test Center"

### Two settings on every item

| Setting | Values | Meaning |
| --- | --- | --- |
| Status | Enabled · Disabled | Disabled = off for everyone. Admins can still edit it; nobody can open or run it. |
| Visibility | Show · Hide · Restrict | **Show**: every signed-in user. **Hide**: no one sees it in menus or lists; Admins can still manage it from the console. **Restrict**: only its assignments. |

New items default to **Restrict** with no assignments (only Admins), so nothing is exposed by accident.

### Assignments (Restrict only)

An item set to Restrict is assigned to any mix of:

- **Users** — named people.
- **Groups** — sets of users an Admin creates ("Family", "Lab crew"). Flat; groups can't contain groups.
- **Roles** — the 5 built-in roles (Admin, Operator, Household member, Guest, Auditor), which act as groups that ship with CAVE. Every user has exactly one role.
- **Screens** — enrolled devices such as a wall tablet (see "Screens").

Phase 1 has include assignments only. Exclude assignments are a later addition.

**Access is binary: can use or can't use.** There are no view / run / edit levels. Using a console section means using everything in it (for example, using Automations means creating, editing and running automations).

**Those who can't use a Restricted item** either see it locked or don't see it at all, set per item:

| "Others see it" | Effect for anyone not assigned |
| --- | --- |
| Locked (default) | Listed with its name and a "Restricted" badge; can't be opened, run or edited |
| Not at all | Absent from menus, lists, search and API listings |

So an item's Visibility is effectively **Show** (everyone uses it), **Hide** (no one but Admins), or **Restrict** (assignees use it; others see it locked or not at all).

### Network condition

Any item can also carry a condition: **Anywhere** (default) or **Local network only**.

- An Admin keeps a list of local address ranges in System › Networks, pre-filled from CAVE's own interfaces (for example `192.168.1.0/24`). VPN ranges (WireGuard, Tailscale) are added by hand; CAVE does not guess.
- A request from outside those ranges is refused for that item, even if every other check passes.
- **The network condition is always in addition to identity, never instead of it.** Being on the network grants nothing by itself.
- System › Networks also lists **trusted proxies**. CAVE reads the client address from `X-Forwarded-For` only when the request comes from a trusted proxy; otherwise it uses the socket address. With no trusted proxies listed, forwarded headers are ignored.

### Control comes through items

Nobody gets a per-device or per-entity permission list. Instead:

- A user, screen or API token may run a command on an entity **only if** it can currently use an item that contains that entity: a dashboard with a card for it, or an action whose steps target it.
- The server checks this on every command, from every path (console, dashboard, raw REST, WebSocket).
- Example: the "Garage Door Control" dashboard has the garage opener on it and is assigned only to the Garage tablet with "Local network only". The Kids dashboard has no garage card. So nothing reached through the Kids dashboard can open the garage — not the tablet, not the web portal, not the API.
- **Admins** have full control everywhere so they can fix things. Operators are not special here; they get what their assignments give them.
- **API tokens** act as their owner and can never exceed what the owner can reach.
- Running an action checks the action item, not each entity inside it. Assigning "Close garage" to someone lets them close the garage through that action only.
- **No back door through the editors** (builder's call, a security rule): saving an automation, sequence, script or dashboard is refused unless the person saving it can already control every entity it targets. Otherwise anyone with the Automations section could write "open the garage" and run it. Admins pass automatically.

### What people see of devices they can't control

- Entities a principal can control show in full: state, attributes, commands.
- Every other entity shows only that it **exists and is restricted**: its name, its room and a "Restricted" badge. No state (the garage tablet's open/closed is not visible to others), no attributes, no list of commands.
- This applies everywhere state leaves the server: REST lists, the WebSocket feed (restricted entities send no `state_changed` events to that principal), search, and dashboard cards (a card for a restricted entity renders as a locked tile).
- Templates are rendered on the server. A template in a card can read only entities the viewer can control; others render as `restricted`.

### Effective access, step by step

For a request by principal P (user, screen or token) on item I:

1. If P is a disabled user, a revoked screen or an expired guest → deny.
2. If P is an Admin → allow (still subject to Status = Disabled for running, and still logged).
3. If I is Disabled → deny.
4. If I has "Local network only" and the client address isn't in a local range → deny.
5. Visibility Show → allow. Hide → deny (Admins handled in step 2). Restrict → allow only if P, P's groups, P's role, or (for screens) the screen itself is assigned; otherwise deny, and list the item as locked or omit it per its "Others see it" setting.

### Starting assignments for built-in items (builder's call)

Built-in console sections and features ship set to Restrict, "Others see it: Not at all", with these role assignments, which an Admin can change:

| Role | Assigned at install |
| --- | --- |
| Admin | Everything (implicit) |
| Operator | Devices, Automations (incl. Test Center), Scripts, Dashboards sections |
| Household member | The Home dashboard |
| Guest | Nothing (an Admin assigns dashboards per guest) |
| Auditor | Audit log, Sign-in log, Run history (read-only by nature) |

Users and permissions and System stay Admin-only by default.

### Where access settings live (builder's call, confirmed by author review)

- Status, Visibility, assignments and the network condition live in the **database**, not in `/config` files, because they point at users, groups and screens and every change must be audited.
- `/config` YAML holds content only (what a dashboard shows, what an automation does). The framework's `visible_to` key is dropped from the dashboard schema.
- A new file found in `/config` becomes an item with the default (Restrict, no assignments). Hand edits to files are detected on reload and written to the audit log as file changes; they can never widen access.

### Safety rules (kept from the framework)

- The last enabled Admin can't be disabled, demoted, or lose Users and permissions or System.
- Disabling a user or revoking a screen ends its sessions at once.
- Changes apply immediately; open sessions receive the update over the WebSocket.
- Every change goes to the audit log with who, what, old value and new value.

## Screens (device assignments)

A **screen** is a client device such as a wall tablet that signs in as itself, without a person.

**Enrollment**

1. An Admin adds a screen ("Garage tablet") in Users and permissions › Screens. CAVE shows a one-time QR code and link that expire in 10 minutes.
2. The tablet opens the link. Its browser creates an **ECDSA P-256 key pair with WebCrypto, marked non-extractable**, and keeps it in IndexedDB. The private key never leaves the browser, and even CAVE's own JavaScript can't read it.
3. The tablet sends the public key. CAVE stores the public key and its SHA-256 fingerprint (the "secure hash" shown in the console). It does not use MAC addresses or serial numbers: browsers can't read them and MACs are easy to fake.
4. The screen stays **Pending** until an Admin approves it in the console. Approval, enrollment and revocation go to the audit log.

**Signing in**

- On every connect, and at least every 12 hours on an open session, CAVE sends a random single-use challenge; the tablet signs it; CAVE verifies it against the stored public key. Replayed or copied answers fail.
- A screen sees only items assigned to it (or set to Show). It never sees the admin console.
- Revoking a screen deletes its public key and ends its sessions.

## HTTPS

Screen keys need a secure context, and dashboard traffic on the LAN must not be readable or alterable by someone on the network, so CAVE serves HTTPS only.

- **Phase 1 does not create a local certificate authority.**
- Out of the box CAVE generates a self-signed certificate on first run and shows its fingerprint in the console, so the user can compare it when the browser warns once.
- The install guide documents the stronger option: the user's own certificate (for example a real domain via a reverse proxy using a DNS challenge), mounted into CAVE or terminated at the proxy listed as trusted.
- Plain HTTP is not offered.

**Must verify early (spike):** that WebCrypto non-extractable keys and IndexedDB work on a page served with a user-accepted self-signed certificate in current Safari (iPadOS), Chrome (Android) and Fire tablets. If any of them refuses, screen enrollment on that browser requires the user's own certificate, and the docs say so.

## Actions dashboard

The everyday screen for household members and screens: a grid of **standard actions** in plain words ("All lights off", "Goodnight", "Shut down lab"), each with a Run button and a short line underneath (what it touches, or last result for scripts). Sections group them ("Everyday", "Lab").

- An action card references an automation, sequence or script that's runnable on demand.
- A card appears only if the viewer can use that action item; the dashboard itself also follows the access model.
- Confirmation before running anything marked `confirm: true` in its YAML (scripts default to true).
- Mockup: `.superpowers/brainstorm/phase1-screens.html`, section 1.

## Test Center

Replaces the demo house. Lives under Automations › Test Center, gated by the "Use the Test Center" feature item.

- **Pick** a real automation or sequence, **saved or draft** (unsaved editor changes).
- **Simulate inputs:** the trigger (for example `binary_sensor.ups_on_battery` → `on` for 2 min) and any entity states conditions or templates read (for example `sensor.ups_battery_runtime_min = 12`). Unset entities use their current real state.
- **Choose scope:** the whole automation, or one step (and the steps nested inside it). When starting mid-way, variables set by skipped steps can be filled in by hand.
- **Run what-if.** The engine runs the real trigger, condition, template and flow logic but swaps every side effect for a log line:
  - entity commands → `What if: turn_off switch.proxmox_vm_media`
  - notifications, webhooks → shown with their final rendered text, not sent
  - scripts → not run; the step returns **sample output** taken from the script header's `sample:` block (new header key), or values the tester types, so later steps can use `result_var`
  - delays and waits → skipped instantly, shown with their duration
- The run ends with a summary: devices changed, messages sent, scripts run — which must always be 0.
- What-if runs are recorded as traces marked "Test", never fire other automations, and never change real state.
- Mockup: `.superpowers/brainstorm/phase1-screens.html`, section 3.

## Scripts (Phase 1 subset)

As in the framework's Scripts section, limited to the **sandbox** target: the `cave-script-runner` container with pwsh 7, python3 and bash, scripts mounted read-only, no Docker socket, CPU and memory limits, the `cave:` header, params as `CAVE_PARAM_*` env vars and JSON on stdin, last stdout line as the JSON result, exit code 0 = success, timeout from the header. One addition: an optional `sample:` block in the header for the Test Center.

## Devices: MQTT

- Mosquitto sidecar (Compose profile `mqtt`), with a user and password created by the installer.
- CAVE subscribes to the MQTT discovery topic format (`homeassistant/<component>/.../config`), which Zigbee2MQTT, Tasmota, Shelly and ESPHome already publish, and maps those components onto CAVE capabilities: `light`, `switch`, `sensor`, `binary_sensor`, `cover`, `lock`, `button`.
- Manually defined MQTT entities in YAML for devices without discovery.

## Notifications in Phase 1 (builder's call)

- The `notify` action exists with one built-in target, `notify.cave`: the console's notification bell, delivered to users the automation names (or to its owners by default). ntfy, SMTP and others arrive with Phase 2 integrations.
- Outgoing `webhook` actions are out of Phase 1; MQTT publish (`mqtt.publish`) is the way to signal outside systems.

## Console sections in Phase 1

| Section | Contents |
| --- | --- |
| Home | Health tiles: MQTT connected, devices unavailable, automation failures (24 h), screens pending approval |
| Dashboards | List, edit (YAML tab), access settings |
| Devices | All devices, by area, unavailable; entity rename and area assignment |
| Automations | Automations, Sequences, Run history (traces), Test Center |
| Scripts | List, editor, Test run, run history |
| Users and permissions | Users, Groups, Screens, Access (every item with Status / Visibility / assignments / network condition), API tokens, Audit log, Sign-in log |
| System | Networks (local ranges, trusted proxies), Certificate, General (location, time zone, units) |

Mockups for the shell and several sections exist in `design/admin-console/`. The Access table follows `.superpowers/brainstorm/phase1-screens.html`, section 2, with assignments split into Users / Groups / Roles / Screens.

## Exit gate for Phase 1

With the internet unplugged on a Debian 13 box running the Compose stack:

1. A Zigbee2MQTT lamp appears through MQTT discovery and toggles from an Actions dashboard.
2. The "Garage Door Control" scenario holds: the dashboard is assigned only to an enrolled tablet with "Local network only". Then each of these is refused by the server, and covered by automated tests:
   - a household member's browser
   - a second, unenrolled tablet on the LAN
   - the enrolled tablet's session from outside the local range
   - a raw API call with another user's token
   - a command sent through the Kids dashboard
3. The UPS-on-battery automation from the framework, adapted for Phase 1 (notifications go to `notify.cave`; the `disk-report.sh` cave-host step is removed; UPS entities come from MQTT), runs in the Test Center against simulated inputs, both whole and step 2 only, with a summary of 0 changes, 0 messages, 0 scripts.
4. A PowerShell script runs from a dashboard button in the sandbox and its result shows in the audit log.

## Later phases (outline only)

- **Phase 2:** the first batch of integrations, picked from a rebuilt list of 30: the easiest, most open and most popular local integrations available today, chosen by research before Phase 2 starts (this replaces the framework's catalog). Setup wizard network scan.
- **Phase 3+:** SSO, passkeys, SSH and CAVE-host script targets, visual builder, history, backups, native packages, the remaining integrations, optional local CA.

## Left to the builder

- Internal module layout, within the framework's repo layout.
- Database schema details for items, assignments and screens.
- How Test Center isolation is implemented (for example, a side-effect-free action executor), as long as the zero-side-effects guarantee is tested.
- Which existing mockups need updating, and in what order screens are built.
- CI details beyond: ruff, mypy --strict for core, pytest, console lint and tests, multi-arch image build.

## Open before going public

- Name and trademark check for "CAVE" (GitHub org, PyPI, Docker Hub, GHCR).
- GitHub organization or account to publish under.
