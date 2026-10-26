# CAVE — Design Framework

Oct 7, 2026 · Justin Coffield

> Markdown copy of the live doc: https://claude.ai/code/artifact/30682ea2-514e-40a9-b4fa-58107f50b8f3
> The live doc holds the drawn architecture and roadmap diagrams; text versions are included below.

CAVE is a self-hosted smart-home hub that runs on hardware you own and works without a vendor cloud. Everyone lands on a dashboard; setup lives in an Intune-style admin console behind sign-in and per-user permissions. It aims to be easy on day one — a setup wizard, plain-language screens and ready-made recipes — while giving tinkerers YAML and scripts in PowerShell, Python or Bash. It installs on Debian 13 minimal, with Docker or as native packages, using only open-source components. This framework is written for open-source contributors and for Claude Code to build from, so each section ends in a concrete contract.

## Goals and scope

CAVE v1 controls a house locally from one Docker host, with no vendor cloud required for anything that has a local API.

**Design principles**

1. **Local first.** Every integration declares its connectivity class. Cloud ones are opt-in and badged in the UI.
2. **Dashboard first, admin console second.** Everyone lands on a dashboard; setup lives in the admin console, opened from the menu bar by people allowed to use it.
3. **Config as code.** Dashboards, automations and scripts live in files under `/config`, are Git-friendly, and round-trip with the UI editors.
4. **Reuse, don't rebuild.** Zigbee, Z-Wave, Matter and cameras run as proven open-source sidecar containers. CAVE talks to them over MQTT or WebSocket.
5. **Crash isolation.** A broken integration restarts on its own and never takes the core down.
6. **Admin-grade UX.** The console behaves like an enterprise admin center: list views, filters, blades, audit log, role-based access.
7. **Bring your own scripts.** PowerShell, Python and Bash scripts are first-class automation steps, with one input/output contract for all three.

**In scope for v1**

- Device and entity registry, areas, labels
- First-run setup wizard, dashboard-first UI, Simple and Advanced editors, automation recipes
- YAML dashboards with a visual editor
- Automation engine (triggers, conditions, actions, sequences)
- Script library: PowerShell 7, Python 3 and Bash, run in a sandbox, on remote hosts over SSH, or on the CAVE host
- The 27 requested integrations in the catalog below, plus MQTT, Matter and RTSP/ONVIF cameras
- Sign-in (local accounts, optional SSO), 5 roles with per-user on/off toggles, audit log, backups
- Debian 13 minimal install, via Docker Compose or native .deb packages, on amd64 and arm64

**Out of scope for v1** (unlike Home Assistant and Gladys)

- Add-on store or OS image (CAVE installs on Debian minimal, with or without Docker)
- Voice assistant and local LLM
- Native mobile apps (the console is a responsive PWA)
- Energy dashboard beyond solar, battery and UPS cards
- Hosted remote-access relay (use your own reverse proxy, WireGuard or Tailscale)

## User experience

Everyone lands on a **dashboard**: rooms, scenes, cameras and quick actions, in plain language. Setup lives in the **admin console**, opened from the menu bar by people whose permissions allow it. Inside the console, editors offer a **Simple** view (sentence builder, forms) and an **Advanced** view (YAML, scripts, traces).

| | Dashboard | Admin console |
| --- | --- | --- |
| Who uses it | Everyone who signs in, plus wall tablets in kiosk mode | Admins, plus any section an Admin turns on for a user |
| What you see | Rooms, devices, scenes, cameras, energy, quick-action buttons | Devices, integrations, automations, scripts, users, system settings |
| Names shown | "Kitchen lights" | Plain names; entity IDs like `light.kitchen_island` in the Advanced view |
| Automations | Run scenes and approved buttons | Recipes and sentence builder (Simple), visual builder and YAML (Advanced) |
| Scripts | Run approved scripts from a button | Write, test, schedule and debug |

**First-run setup wizard** (goal: a working dashboard in under 15 minutes)

1. Create the owner account (password plus authenticator app).
2. Set home location, time zone and units.
3. Scan the network. CAVE lists what it found (Hue bridge, Sonos, TVs, UPS) and asks "Add these?"
4. Pick the radios you own (Zigbee, Z-Wave, Thread). CAVE turns on the matching containers.
5. Name rooms and drag devices into them.
6. Choose starter recipes. CAVE builds a Home dashboard from your rooms.

**Recipes** are ready-made automations with blanks to fill in. They save as normal YAML, so anyone can open and change them later. v1 ships with:

- Turn lights on at sunset and off at a set time
- Notify me when the washer or dryer finishes
- Alert me and shut down servers when the UPS is on battery
- Turn everything off when the last person leaves
- Notify me when a door opens while I'm away
- Run a script on a schedule

**Sentence builder** (the Simple automation view): "When **UPS** **switches to battery** for **2 minutes**, if **runtime is under 15 minutes**, then **notify me** and **run Lab safe shutdown**." Each bold word is a picker that shows names, never IDs.

**Friendly-by-default rules**

1. Plain names everywhere on dashboards and in Simple views; entity IDs appear only in Advanced views.
2. Every error says what happened and what to do next: "Hue bridge stopped answering. Check it's powered on, then select Retry."
3. Risky actions (delete, run a script on the CAVE host) ask for confirmation and show what will change.
4. Undo for the last 20 configuration changes, backed by the audit log.
5. Every screen works on a phone; dashboards install as an app (PWA).
6. Each page has a help link to its matching docs page.
7. Accessible: full keyboard use, screen-reader labels, 4.5:1 text contrast, light, dark and high-contrast themes.

**Words we use** (the UI says the left column; docs and code use the right)

| UI word | What it means | Technical term |
| --- | --- | --- |
| Device | A physical thing: bulb, TV, UPS | Device |
| Control or reading | One thing a device can do or report | Entity |
| Room | Where a device lives | Area |
| Connection | A link to a brand or service | Integration instance |
| Automation | "When this happens, do that" | Automation |
| Routine | A reusable list of steps | Sequence |
| Script | Your own PowerShell, Python or Bash code | Script |

## Navigation, sign-in and permissions

CAVE opens to the signed-in person's default dashboard. A slim menu bar holds everything else, and the admin console is one click away for people allowed to use it. All sign-in and permission parts are open source and run on the CAVE box itself.

**Menu bar** (left to right)

1. CAVE logo — back to your default dashboard.
2. Dashboards — a switcher that lists only the dashboards you can open.
3. Admin console — shown only if at least one console section is on for you.
4. Notifications bell.
5. Your name — profile, password and MFA, theme, default dashboard, sign out.

**Addresses**

| Path | Opens |
| --- | --- |
| `/` | Your default dashboard |
| `/d/<slug>` | A specific dashboard, or a "not available to you" page if it's turned off for you |
| `/admin/...` | Admin console sections |
| `/login` | Sign-in |
| `/kiosk/<token>` | One dashboard on a wall tablet, with no menu bar |

**Kiosk mode** for wall tablets: an Admin issues a device token tied to one dashboard. It can't open the admin console, expires after 90 days by default, and can be revoked from Users and permissions.

**Built-in sign-in**

1. Username and password, hashed with Argon2id (`argon2-cffi`).
2. Second factor with an authenticator app (TOTP, `pyotp`): required for Admins and Operators, optional for everyone else. Passkeys and security keys (WebAuthn, `py_webauthn`) are an option.
3. Ten one-time recovery codes are issued when MFA is set up.
4. Lockout: 5 failed attempts locks the account for 15 minutes; every attempt goes to the sign-in log.
5. Sessions use a secure, HttpOnly, SameSite=Strict cookie with a 12-hour idle timeout.
6. The setup wizard creates the first Admin. A forgotten Admin password is reset by another Admin, or with `cave user reset-password <name>` on the Debian host.

**Single sign-on (optional)** over OpenID Connect, using your own open-source identity provider:

| Provider | License | Good fit |
| --- | --- | --- |
| [Authelia](https://github.com/authelia/authelia) | Apache-2.0 | Lightweight; OpenID Certified; TOTP and passkeys built in |
| [authentik](https://github.com/goauthentik/authentik) | MIT (core; enterprise features use a separate license) | Full web UI for users and groups |
| Keycloak | Apache-2.0 | Larger setups; heavier Java service |

- A group claim from the provider maps to a CAVE role, for example `cave-admins` → Admin. Per-user toggles still apply on top.
- One local "break-glass" Admin always works, even when the identity provider is down.

**Roles set the defaults**

| Area | Admin | Operator | Household member | Guest | Auditor |
| --- | --- | --- | --- | --- | --- |
| Dashboards | All | All | Assigned | Assigned | View all |
| Device control | Full | Full | Allowed rooms | Assigned dashboards only | — |
| Automations | Edit | Edit | Run | — | View |
| Scripts | Edit and run | Run | Approved buttons | — | View |
| Integrations | Manage | View | — | — | View |
| Users and permissions | Manage | — | — | — | View |
| System administration | Manage | — | — | — | View |
| Audit log | View | — | — | — | View |

Guest accounts also carry an expiry date.

**Per-user toggles.** Each user's page shows three groups of on/off toggles. Every toggle starts at the role default; changing one marks it **Custom**, and **Reset to role default** clears it.

| Group | One toggle per | Examples |
| --- | --- | --- |
| Dashboards | Dashboard | Home, Power, Cameras, Kids' room |
| Admin console sections | Console section | Devices, Integrations, Automations, Scripts, Users and permissions, System administration |
| Features | Capability | Control devices, View cameras live, Run scripts, Edit automations, Create API tokens, Get notifications |

**Permission rules**

1. The server checks every request against the person's effective permissions. Hiding a menu item is only cosmetic.
2. Effective permission = the user's toggle if one is set, otherwise the role default.
3. Admins can't lose Users and permissions or System administration, and CAVE won't disable or demote the last enabled Admin.
4. One toggle disables a whole account; its sessions end immediately.
5. Changes apply at once: open sessions receive the update over the WebSocket.
6. Every change goes to the audit log with who, what, the old value and the new value.

**Data and API**

```yaml
# permission keys
dashboard:<slug>      # dashboard:power
console:<section>     # console:integrations
feature:<name>        # feature:scripts.run
```

Tables: `users` (id, username, display_name, role, enabled, expires_at, mfa), `permission_overrides` (user_id, key, allowed, set_by, set_at) and `sessions`.

| Method + path | Purpose |
| --- | --- |
| `POST /api/v1/auth/login`, `/auth/mfa`, `/auth/logout` | Sign in, second factor, sign out |
| `GET /api/v1/me` | Profile and effective permissions |
| `GET/POST/PATCH /api/v1/users` | Manage users (Admin) |
| `GET/PUT /api/v1/users/{id}/permissions` | Read or set toggles |
| `POST /api/v1/users/{id}/permissions/reset` | Back to role defaults |
| `POST /api/v1/kiosk-tokens` | Issue a wall-tablet token |

## Tech stack

Recommendation: Python 3.13 (asyncio) for the core and integrations, TypeScript + React + Fluent UI v9 for the console. Python wins because most of the requested integrations already have maintained, standalone async Python libraries; Fluent UI is Microsoft's open-source (MIT) design system and gives the Intune look without copying Microsoft branding.

| Option | Integration libraries | Contributor pool | Scripting support | Verdict |
| --- | --- | --- | --- | --- |
| **Python core** | Best: pyatv, aiohue, aiounifi, pyenphase, plexapi, proxmoxer, thinqconnect, aiowebostv and more already exist | Largest in home automation | Runs `pwsh` (plus Python and Bash) in a sidecar runner | **Recommended** |
| Node.js / TypeScript core | Good for Zigbee and Matter (matter.js), thin elsewhere | Large, web-heavy | Same sidecar approach | Viable; more ports to write |
| .NET / C# core | Thin for consumer devices | Smaller in this space | Native PowerShell hosting | Not recommended for core; fine for a future plugin host |
| Go core + plugins | Very thin | Small | Sidecar | Fast, but most integrations would be rewritten |

**Stack decisions**

| Layer | Choice |
| --- | --- |
| Core runtime | Python 3.13, asyncio, uvloop |
| API | FastAPI (REST + OpenAPI 3.1), native WebSocket endpoint |
| Validation | Pydantic v2 models; JSON Schema exported for YAML files |
| Templates | Jinja2 in sandboxed mode (familiar to Home Assistant users) |
| Storage | SQLite (WAL) by default; PostgreSQL optional for large installs |
| History | Same database, 10-day raw retention, 5-minute rollups kept 1 year |
| Message bus | In-process async event bus; Mosquitto MQTT broker as a sidecar for Zigbee2MQTT and external devices |
| Console | React 19, TypeScript, Fluent UI React v9, TanStack Query, Vite |
| Dashboard grid | react-grid-layout; charts with Apache ECharts |
| Packaging | Multi-arch OCI images (amd64, arm64) built in GitHub Actions |
| License | Apache-2.0 for CAVE; copyleft libraries run out-of-process (see Open decisions) |

## Architecture

Integrations run outside the core, so one failure never stops the house. Interactive version: `design/architecture-board.html`.

```text
Clients:        Admin console (React + Fluent UI) | Dashboards (YAML, PWA) | Scripts and webhooks (REST, IFTTT, Automate)
                        │ REST + WebSocket
cave-core:      API · Automation engine · State + registry · Config loader · Host supervisor
                        │ JSON-RPC over a local WebSocket
Integration hosts: Shared host (ntfy, SMTP, NUT, Docker) | Dedicated hosts (Hue, UniFi, Plex, Sonos, TVs, Proxmox) | Cloud hosts (EcoFlow, ThinQ, Spotify, iCloud)
                        │ MQTT, WebSocket, HTTP
Sidecars:       Mosquitto · Zigbee2MQTT · Z-Wave JS UI · Matter Server · go2rtc · script-runner (pwsh, Python, Bash) · docker-proxy · postgres
                        │ USB sticks, RTSP streams, LAN
Devices:        Local network devices | Radio and camera devices | Vendor clouds (opt-in)
```

Clients only talk to the core's API. Integrations run in host processes that the supervisor restarts on failure; radios, cameras and scripts run in sidecar containers (scripts can also run over SSH); vendor clouds sit on a separate, opt-in path.

## Core data model

Everything the house exposes is an **entity** with a typed **capability**, owned by a **device**, created by an **integration instance**. Automations and dashboards only ever reference entity IDs, so swapping a Hue bulb for a Zigbee bulb doesn't break anything.

| Object | Key fields | Example |
| --- | --- | --- |
| Integration instance | `id`, `domain`, `config` (encrypted), `status`, `iot_class` | `hue.bridge_upstairs` |
| Device | `id`, `integration_id`, `manufacturer`, `model`, `sw_version`, `area_id`, `via_device_id` | Hue bridge, then bulbs via it |
| Entity | `entity_id`, `device_id`, `capability`, `name`, `area_id`, `labels[]`, `enabled`, `hidden` | `light.kitchen_island` |
| State | `entity_id`, `value`, `attributes{}`, `last_changed`, `last_updated`, `context_id` | `on`, `{brightness: 180}` |
| Area / Floor | `id`, `name`, `floor`, `icon` | Kitchen, Floor 1 |
| Label | `id`, `name`, `color` | `night-mode`, `kids` |
| Event | `type`, `data{}`, `origin`, `context_id`, `time_fired` | `state_changed`, `automation_triggered` |
| Context | `id`, `parent_id`, `user_id` | Traces who or what caused a change |

**Capabilities for v1** (the entity_id prefix)

- Control: `light`, `switch`, `fan`, `cover`, `lock`, `climate`, `media_player`, `button`, `number`, `select`, `scene`
- Read: `sensor`, `binary_sensor`, `device_tracker`, `weather`, `camera`, `update`, `event`
- Service: `notify`, `script`, `automation`

Each capability defines its states, attributes and commands in a shared schema file, for example `light` commands: `turn_on(brightness?, color_temp_k?, rgb?, transition?)`, `turn_off(transition?)`, `toggle()`.

**IoT class** (shown as a badge on every integration and device)

- `local_push`, `local_poll` — no internet needed
- `cloud_push`, `cloud_poll` — needs the vendor cloud; flagged orange in the console

## Integration framework

Integrations are Python packages that run inside **integration host** processes, not inside the core. The host talks to the core over a local WebSocket using JSON-RPC 2.0, so a crash, memory leak or blocking call stays contained. The same protocol lets future integrations be written in any language.

**Manifest** (`integrations/<domain>/manifest.yaml`)

```yaml
domain: hue
name: Philips Hue
version: 0.1.0
codeowners: ["@github-handle"]
iot_class: local_push
capabilities: [light, sensor, binary_sensor, scene, button]
discovery:
  mdns: ["_hue._tcp.local."]
config_flow: true          # UI setup wizard
requirements: ["aiohue==4.*"]   # pin exact version in lockfile
host: shared               # shared | dedicated | sidecar
license_check: passed
```

**SDK contract** (what every integration implements)

1. `async_setup(instance)` — connect, authenticate, return devices and entities.
2. `async_unload()` — close sockets and timers cleanly.
3. `ConfigFlow` steps — discovery confirm, credentials, pairing (for example, press the Hue link button).
4. `Entity` subclasses per capability — push state with `self.publish_state()`, implement commands like `async_turn_on()`.
5. `diagnostics()` — redacted dump for support bundles.

**Lifecycle states** shown in the console: `Not configured` → `Setting up` → `Connected` → `Degraded` (retrying with backoff) → `Failed` (needs user action, such as re-auth) → `Disabled`.

**Host types**

- `shared` — several lightweight integrations in one host process (ntfy, SMTP, OpenWeather).
- `dedicated` — one integration per process, for chatty or fragile libraries (UniFi, Plex).
- `sidecar` — a separate container CAVE connects to (Zigbee2MQTT, Z-Wave JS UI, Matter Server, go2rtc, script runner).

**Quality tiers** (shown on the catalog card, so users know what they're installing)

- Bronze: config flow, unit tests, docs page
- Silver: re-auth flow, diagnostics, 90% test coverage of entity mapping
- Gold: discovery, recorded fixture tests against a real device, translations

## Integration catalog

24 of the 30 integrations work with no internet; 6 depend on a vendor cloud and are opt-in. Phases map to the Roadmap section. Library licenses still need the Phase 0 license review.

| Integration | Protocol / API | IoT class | Auth / pairing | Library or sidecar | Phase |
| --- | --- | --- | --- | --- | --- |
| MQTT | MQTT 3.1.1 / 5 via Mosquitto | local_push | User + password, TLS | aiomqtt | P2 |
| Zigbee | Zigbee2MQTT over MQTT; USB or network coordinator | local_push | MQTT credentials | Zigbee2MQTT sidecar | P2 |
| Philips Hue | Hue Bridge CLIP API v2 (HTTPS + SSE event stream) | local_push | App key via bridge link button | aiohue | P2 |
| TP-Link Kasa / Tapo | Kasa local protocol; Tapo KLAP local handshake | local_poll | Tapo needs TP-Link account credentials | python-kasa (GPL-3.0) | P2 |
| ntfy | HTTP publish; JSON stream / WebSocket subscribe | local_push | Access token or basic auth | httpx | P2 |
| SMTP email | SMTP with STARTTLS or implicit TLS | local_push (outbound) | User + app password | aiosmtplib | P2 |
| OpenWeather | One Call API 3.0 | cloud_poll | API key | httpx | P2 |
| Network UPS Tools | NUT protocol, TCP 3493 | local_poll | upsd user + password | aionut | P2 |
| Docker | Docker Engine API through a socket proxy; event stream | local_push | Read-only socket proxy | aiodocker | P2 |
| Z-Wave | zwave-js server WebSocket | local_push | Inclusion with S2 PIN / QR | Z-Wave JS UI sidecar + zwave-js-server-python | P3 |
| Scripts (PowerShell, Python, Bash) | Params in, JSON out; runs in the sandbox runner, on SSH hosts, or on the CAVE host | local_push | Runner token; SSH keys kept in CAVE secrets | cave-script-runner sidecar (new) + asyncssh | P3 |
| UniFi Network | UniFi Network local API (official Integration API, plus classic controller API for events) | local_push | API key from Network > Settings > Integrations | aiounifi | P4 |
| AdGuard Home | REST API (OpenAPI) | local_poll | Basic auth | adguardhome | P4 |
| Proxmox VE | REST API | local_poll | API token (`user@realm!token`) | proxmoxer | P4 |
| Synology DSM | DSM Web API (`SYNO.*`) | local_poll | DSM account; 2FA device token | py-synologydsm-api | P4 |
| Nginx | `stub_status` metrics; CAVE also documents Nginx as its reverse proxy | local_poll | None or basic auth | httpx | P4 |
| Sonos | UPnP/SOAP on port 1400 with event subscriptions | local_push | None | SoCo | P4 |
| Plex | Plex Media Server HTTP API + WebSocket notifications | local_push | X-Plex-Token | plexapi | P4 |
| Jellyfin | REST API + WebSocket | local_push | API key | jellyfin-apiclient-python | P4 |
| LG webOS TV | SSAP over WebSocket (ports 3000/3001); Wake-on-LAN | local_push | Accept prompt on TV | aiowebostv | P4 |
| Samsung Smart TV | Tizen remote WebSocket (ports 8001/8002); Wake-on-LAN | local_push | Accept prompt on TV; token stored | samsungtvws | P4 |
| Apple TV | MRP / Companion / AirPlay protocols | local_push | PIN pairing | pyatv | P4 |
| Spotify | Spotify Web API | cloud_poll | OAuth 2.0 (PKCE); Premium for playback control | spotifyaio | P4 |
| Matter | OHF Matter Server (matter.js) WebSocket; Thread needs a border router | local_push | Matter setup code / QR | Matter Server sidecar | P5 |
| Cameras (RTSP / ONVIF) | RTSP in, WebRTC / MSE out to the browser | local_push | Camera user + password | go2rtc sidecar + onvif-zeep-async | P5 |
| Enphase IQ Gateway | Local HTTPS API on the gateway | local_poll | JWT token from Enlighten (1 year on D7 firmware) | pyenphase | P5 |
| EcoFlow | EcoFlow Open Platform REST + MQTT; no LAN-only path | cloud_push | Access key + secret key (developer approval can take about a week) | Custom client | P5 |
| LG ThinQ appliances | ThinQ Connect API + MQTT events | cloud_push | Personal Access Token | thinqconnect (LG official) | P5 |
| Apple iCloud | Unofficial iCloud web endpoints (Find My); CalDAV for calendars | cloud_poll | Apple ID + 2FA; app-specific password for CalDAV | pyicloud | P5 |
| IFTTT | Webhooks: outbound trigger, inbound needs CAVE reachable over HTTPS | cloud_push | Webhook key (may need a paid IFTTT plan) | httpx | P5 |

**Risk notes**

- Apple iCloud is unofficial and breaks when Apple changes endpoints; accounts with Advanced Data Protection may block web access. Ship it as "Experimental".
- EcoFlow, LG ThinQ and Spotify can change cloud terms or rate limits; keep their clients thin and well-tested against recorded fixtures.
- python-kasa is GPL-3.0. Keep it in its own integration host and settle the license approach before Phase 2 (see Open decisions).
- "IFTTT Automate" is read here as IFTTT Webhooks. If you meant the LlamaLab Automate Android app, it can call the same CAVE webhook endpoint.

## Dashboard YAML spec

Each dashboard is one file in `/config/dashboards/`, validated against a published JSON Schema, with a theme file controlling look and a grid controlling layout. The visual editor writes the same YAML back, preserving comments.

**Rules**

1. One file per dashboard: `dashboards/<slug>.yaml`. The file name is the URL: `/d/<slug>`.
2. Structure: `dashboard` → `views[]` → `sections[]` → `cards[]`.
3. Layout uses a 12-column grid; each card sets `w` and `h`. Phones collapse to 1 column.
4. `visible_to` limits a dashboard or view to roles or users.
5. `visibility` on any card shows it only when conditions pass (state, user, screen width).
6. Themes live in `/config/themes/<name>.yaml` and map to Fluent design tokens.
7. Unknown keys fail validation with a line number, so typos never silently render nothing.

**Card types for v1:** `tile`, `entities`, `gauge`, `history`, `media`, `camera`, `weather`, `energy`, `button`, `markdown`, `stack`, `conditional`, `iframe`.

**Example**

```yaml
# /config/dashboards/home.yaml
dashboard:
  title: Home
  icon: home
  theme: cave-dark
  visible_to: [household, admin]
  views:
    - id: main
      title: Overview
      sections:
        - title: Living Room
          cards:
            - type: tile
              entity: light.living_room
              tap_action: toggle
              w: 3
              h: 1
            - type: media
              entity: media_player.living_room_tv
              w: 6
              h: 2
            - type: camera
              entity: camera.front_door
              live: true
              w: 3
              h: 2
        - title: Power
          cards:
            - type: energy
              solar: sensor.enphase_production_w
              battery: sensor.ecoflow_battery_pct
              grid: sensor.enphase_net_consumption_w
              w: 6
              h: 2
            - type: gauge
              entity: sensor.ups_load_pct
              min: 0
              max: 100
              severity: { green: 0, yellow: 60, red: 85 }
              w: 3
              h: 2
            - type: tile
              entity: binary_sensor.ups_on_battery
              visibility:
                - condition: state
                  entity: binary_sensor.ups_on_battery
                  state: "on"
              w: 3
              h: 1
```

**Theme example**

```yaml
# /config/themes/cave-dark.yaml
theme:
  name: cave-dark
  base: dark                  # light | dark | high-contrast
  tokens:
    colorBrandBackground: "#0F6CBD"
    colorNeutralBackground1: "#1B1A19"
    borderRadiusMedium: 6px
  card:
    density: comfortable      # compact | comfortable
```

## Automation engine

An automation is **triggers → conditions → actions**; a **sequence** (called a Routine on dashboards and in Simple views) is a reusable, parameterized list of actions that automations call. Both live as YAML in `/config/automations/` and `/config/sequences/`, and every run records a step-by-step trace viewable in the console.

**Building blocks**

| Block | v1 types |
| --- | --- |
| Triggers | `state`, `numeric_state`, `time`, `time_pattern`, `sun` (sunrise/sunset + offset), `event`, `mqtt`, `webhook`, `device` (button press), `zone` (enter/leave), `startup` |
| Conditions | `state`, `numeric_state`, `time` (window + weekdays), `sun`, `template`, `and` / `or` / `not` |
| Actions | `call` (entity command), `notify`, `delay`, `wait_for` (state or event, with timeout), `choose` (if / else-if), `repeat` (count / while / until / for_each), `parallel`, `sequence` (run a routine), `script` (PowerShell, Python or Bash), `webhook`, `set_variable`, `stop` |

**Run modes** (what happens when a trigger fires while a run is active)

- `single` — ignore the new trigger (default)
- `restart` — cancel the running one, start fresh
- `queued` — run after the current one, `max: 10`
- `parallel` — run side by side, `max: 10`

**Example: UPS power loss**

```yaml
# /config/automations/ups-on-battery.yaml
automation:
  id: ups-on-battery
  name: UPS on battery — alert and shut down lab
  mode: single
  enabled: true
  triggers:
    - type: state
      entity: binary_sensor.ups_on_battery
      to: "on"
      for: 00:02:00
  conditions:
    - type: numeric_state
      entity: sensor.ups_battery_runtime_min
      below: 15
  actions:
    - type: notify
      targets: [notify.ntfy_admins, notify.smtp_justin]
      title: "Power outage"
      message: "UPS on battery. {{ states('sensor.ups_battery_runtime_min') }} min left."
    - type: sequence
      ref: sequence.lab_safe_shutdown
      with:
        grace_seconds: 120
    - type: wait_for
      entity: binary_sensor.ups_on_battery
      to: "off"
      timeout: 01:00:00
      on_timeout: stop
    - type: notify
      targets: [notify.ntfy_admins]
      message: "Power restored."
```

**Example: routine with PowerShell and Bash steps**

```yaml
# /config/sequences/lab_safe_shutdown.yaml
sequence:
  id: lab_safe_shutdown
  name: Lab safe shutdown
  fields:
    grace_seconds: { type: int, default: 60 }
  actions:
    - type: call
      target: switch.proxmox_vm_media
      command: turn_off
    - type: script
      ref: scripts/Stop-LabHosts.ps1     # PowerShell, runs in the sandbox
      args:
        GraceSeconds: "{{ grace_seconds }}"
      result_var: lab
    - type: script
      ref: scripts/disk-report.sh        # Bash, runs on the CAVE host
      result_var: disk
    - type: notify
      targets: [notify.ntfy_admins]
      message: "Lab shutdown: {{ lab.status }}. Host disk {{ disk.used_pct }}% used."
```

**Script steps** follow the shared contract in the Scripts section below: params in, one JSON object out, exit code 0 for success.

**Editor UX:** The Simple view offers the sentence builder and recipes; the Advanced view adds a visual builder (When / And if / Then do) and a YAML tab. All three edit the same file. A **Run** button with a **Dry run** toggle executes actions as logged no-ops; in a dry run, script steps show what they would run instead of running it.

## Scripts

Write a script once in PowerShell, Python or Bash, then run it from an automation, a dashboard button, a schedule or the console. It can run in CAVE's sandbox, on another machine over SSH, or on the CAVE host itself.

**Languages**

| Language | Runtime | File | Good for |
| --- | --- | --- | --- |
| PowerShell | PowerShell 7 (`pwsh`); Windows PowerShell 5.1 on Windows hosts over SSH | `.ps1` | Windows hosts, Microsoft APIs, admin tasks |
| Python | Python 3; sandbox scripts can list pip packages in their header | `.py` | APIs, data handling, anything with a pip library |
| Bash / sh | GNU Bash 5 or POSIX `sh` | `.sh` | Linux housekeeping, command-line tools, cron-style jobs |

**Where scripts run**

| Target | How it works | Default | Who can use it |
| --- | --- | --- | --- |
| Sandbox | `cave-script-runner` container with pwsh, python3 and bash; scripts mounted read-only, no Docker socket, CPU and memory limits | On | Operators and Admins |
| Remote host | SSH with a key kept in CAVE secrets; Linux, macOS, NAS, Proxmox, or Windows with OpenSSH | On per host an Admin adds | Admins add hosts; Operators run |
| CAVE host | SSH to the host machine as a restricted `cave-scripts` user; sudo only for commands an Admin lists | Off | Admins only; MFA re-prompt to turn on |

The CAVE host is reached over SSH because the core runs in a container. That keeps one code path for remote and local runs, uses normal Linux permissions, and leaves a sign-in record in the host's own auth log.

**Script header.** Each script starts with a `cave:` comment block. CAVE reads it to build the run form, pick the target and apply limits.

```powershell
<#
cave:
  name: Stop lab hosts
  target: sandbox            # sandbox | ssh:<host-id> | cave-host
  timeout: 5m
  params:
    GraceSeconds: { type: int, default: 60, min: 0, max: 600 }
  secrets: [PROXMOX_TOKEN]
#>
param([int]$GraceSeconds = 60)
# ... shut down VMs ...
@{ status = "3 hosts stopped"; stopped = 3 } | ConvertTo-Json -Compress
```

```python
# cave:
#   name: Check NAS backup age
#   target: ssh:nas01
#   timeout: 2m
#   params:
#     max_hours: { type: int, default: 26 }
import json, os
max_hours = int(os.environ["CAVE_PARAM_MAX_HOURS"])
age_hours = 7  # ... read the newest backup timestamp ...
print(json.dumps({"status": "ok" if age_hours <= max_hours else "stale", "age_hours": age_hours}))
```

```bash
#!/usr/bin/env bash
# cave:
#   name: Disk space report
#   target: cave-host
#   timeout: 1m
#   params:
#     warn_pct: { type: int, default: 85 }
set -euo pipefail
used=$(df --output=pcent / | tail -1 | tr -dc '0-9')
status=ok; [ "$used" -ge "$CAVE_PARAM_WARN_PCT" ] && status=warn
printf '{"status":"%s","used_pct":%s}\n' "$status" "$used"
```

**One contract for every language**

1. **Inputs:** declared params arrive as environment variables `CAVE_PARAM_<NAME>` and as one JSON object on stdin. PowerShell scripts also get them as named parameters. Values are never pasted into a command line.
2. **Secrets:** listed secrets arrive as environment variables, are masked in logs, and never appear in traces.
3. **Output:** the last line of stdout is one JSON object, saved to the step's `result_var`. Other output goes to the run log.
4. **Result:** exit code 0 means success. Anything else fails the step and shows the last 20 log lines.
5. **Timeout:** taken from the header (default 60 s, maximum 1 h). CAVE stops the whole process tree when it's reached.
6. **Run log:** who or what started it, target, parameters (secrets masked), duration, exit code and output.

**Using a script in an automation**

```yaml
- type: script
  ref: scripts/Stop-LabHosts.ps1
  target: sandbox          # optional; overrides the header
  args:
    GraceSeconds: 120
  result_var: lab
- type: notify
  targets: [notify.ntfy_admins]
  message: "Lab shutdown: {{ lab.status }}"
```

**Safety rules**

- Admins create and edit scripts. Operators run them. Household members only see scripts an Admin placed on a dashboard button.
- Scripts live in `/config/scripts/` with the rest of the config; the console shows a diff before every save.
- The CAVE-host target stays off until an Admin turns it on, re-enters MFA and accepts a warning.
- Optional signing: require Authenticode-signed PowerShell and a SHA-256 allow-list for Python and Bash (`require_signed: true`).
- A **Test run** button runs the script with sample params and shows the output before it goes into an automation.

**In the console** (Automations → Scripts): a list with language badge, target, last result and "used by"; an editor with highlighting for all three languages and a form built from the header; a Test run panel with live output; and a Hosts tab to add SSH hosts, test the connection and confirm the host key.

## Admin console

The console copies the Intune admin center's layout patterns — left service nav, blades with a sub-menu, command bar, filterable grids, wizard fly-outs — built with Fluent UI React v9. It uses CAVE's own name, icon and colors; no Microsoft logos or product names. Mockups: `design/admin-console/`.

**Shell**

- Top bar: CAVE logo, a Dashboards link back to the everyday view, global search (devices, entities, automations, settings), notifications bell, settings gear, help, user menu.
- Left nav: collapsible, icons + labels, favorites pinned at top.
- Content: breadcrumb → page title with `…` menu → blade sub-menu on the left → working area on the right.

**Navigation tree**

1. **Home** — health tiles: integrations connected / degraded, devices unavailable, automation failures (24 h), updates available, UPS and solar status.
2. **Dashboards** — list, open, edit, set default per role.
3. **Devices** — All devices · By area · By integration · Unavailable · Discovered (pending adoption).
4. **Entities** — All entities, bulk rename, enable/disable, assign area and labels.
5. **Integrations** — Installed · Catalog (add) · Discovered on network · Health.
6. **Automations** — Automations · Sequences · Scenes · Scripts (PowerShell, Python, Bash) · Run history (traces).
7. **Areas and labels**
8. **Notifications** — targets (ntfy, SMTP, IFTTT) and routing rules.
9. **Reports** — device health, automation runs, energy, integration uptime; export CSV.
10. **Users and permissions** — users, roles, per-user toggles, API tokens, sign-in log.
11. **System administration** — general, network and discovery, backups, updates, secrets, audit log.
12. **Troubleshooting + support** — live logs, diagnostics, support bundle download.

**Page patterns** (reuse everywhere so each new feature costs less UI work)

| Pattern | Used for | Behavior |
| --- | --- | --- |
| List blade | Devices, entities, automations, integrations | Command bar (`+ Add`, Refresh, Export, Columns, Bulk actions), search box, filter pills, sortable grid, paging at 50 rows |
| Object blade | One device, one automation | Left sub-menu (Overview, Properties, Entities, Activity, Diagnostics); "Essentials" panel at top of Overview |
| Create wizard | New integration, automation, user | Fly-out with tabs: Basics → Configuration → Scope (areas, labels, roles) → Review + create |
| Status tiles | Home, Reports | Count + trend + click-through to a pre-filtered list |
| YAML tab | Dashboards, automations, sequences | Monaco editor with schema validation, side-by-side diff before save |

**Who sees what:** the Admin console link in the menu bar appears only for people with at least one console section turned on. Each section, dashboard and feature follows the toggles described in Navigation, sign-in and permissions.

## APIs

The console uses only public APIs, so anything the UI can do, a script can do. REST handles reads and changes; one WebSocket carries live state; webhooks let outside systems trigger automations.

**REST** (`/api/v1`, OpenAPI 3.1 at `/api/v1/openapi.json`)

| Method + path | Purpose |
| --- | --- |
| `GET /devices`, `GET /devices/{id}` | List and read devices (filter: `area`, `integration`, `status`) |
| `GET /entities`, `PATCH /entities/{entity_id}` | List, rename, assign area/labels, enable/disable |
| `GET /states`, `GET /states/{entity_id}` | Current state |
| `POST /entities/{entity_id}/commands/{command}` | Run a command, for example `turn_on` with `{"brightness": 180}` |
| `GET /history?entity_id=&start=&end=` | State history and rollups |
| `GET/POST/PUT/DELETE /automations`, `/sequences`, `/dashboards` | CRUD; body is the YAML document as JSON |
| `POST /automations/{id}/run?dry_run=true` | Manual or dry run |
| `GET /automations/{id}/traces` | Run traces |
| `GET/POST /integrations`, `POST /integrations/{id}/reload` | Manage integration instances |
| `GET /audit` | Audit log (admin only) |
| `POST /backups`, `GET /backups/{id}` | Create and download backups |

**WebSocket** (`/api/v1/ws`)

```json
// client → server
{"id": 1, "type": "auth", "token": "<access token>"}
{"id": 2, "type": "subscribe", "events": ["state_changed"], "filter": {"area": "kitchen"}}
{"id": 3, "type": "command", "entity_id": "light.kitchen_island", "command": "turn_on", "args": {"brightness": 200}}

// server → client
{"id": 2, "type": "event", "event": {"type": "state_changed", "entity_id": "light.kitchen_island",
  "old": "off", "new": "on", "attributes": {"brightness": 200}, "context_id": "01J..."}}
```

**Webhooks** (`POST /api/v1/webhook/{webhook_id}`) — random 32-byte IDs, optional HMAC signature header, rate limited. Used by IFTTT, Automate and any outside system.

**Internal integration-host protocol** — JSON-RPC 2.0 over a local WebSocket: `host.register`, `entity.publish_state`, `entity.command`, `instance.setup`, `instance.unload`, `host.heartbeat` (every 10 s; 3 missed = restart).

## Install on Debian minimal

CAVE targets **Debian 13 "trixie" minimal** on amd64 or arm64. Both install paths use the same config files and the same web console; pick Docker unless you can't or won't run containers.

**Base system** (both paths)

1. Install Debian 13 from the netinst image. In the software selection, tick only **SSH server** and **standard system utilities** (no desktop).
2. Give the box a fixed IP or a DHCP reservation, and set the time zone: `sudo timedatectl set-timezone America/Los_Angeles`.
3. Turn on automatic security updates: `sudo apt install unattended-upgrades`.
4. Add firewall rules with `nftables` (Debian's default): allow SSH and HTTPS 443 from the LAN, plus MQTT 1883/8883 only if LAN devices need it.
5. Plug in radios and note their stable names under `/dev/serial/by-id/`.
6. Download `install.sh`, read it, then run `sudo sh install.sh --docker` or `sudo sh install.sh --native`. It lists every change and asks before making it.

| | Path A: Docker (default) | Path B: native packages |
| --- | --- | --- |
| Best for | Most installs; easiest upgrades and rollbacks | Small boxes, appliance builds, people who avoid containers |
| Installs | Docker Engine (`docker-ce`, `docker-compose-plugin`) from Docker's apt repository | `cave-core` from the CAVE apt repository plus Debian packages |
| Sidecars | Containers, turned on per Compose profile | systemd services |
| Upgrades | `cave upgrade` pulls new images | `sudo apt upgrade` |
| Config and data | `./config` and `./data` | `/etc/cave` and `/var/lib/cave` |
| Script sandbox | `cave-script-runner` container | systemd-sandboxed service |

**Path A: Docker (default).** Docker Engine supports Debian 13 on amd64 and arm64 from [Docker's apt repository](https://docs.docker.com/engine/install/debian/). Compose then runs the containers below; `docker compose --profile zigbee --profile zwave up -d` starts the stack.

**Containers**

| Service | Image | Profile | Why separate |
| --- | --- | --- | --- |
| cave-core | `ghcr.io/<org>/cave-core` (API, console, automation engine, integration hosts) | always | — |
| mosquitto | `eclipse-mosquitto:2` | `mqtt` (auto-on with `zigbee`) | Standard MQTT broker |
| zigbee2mqtt | `koenkk/zigbee2mqtt` | `zigbee` | Owns the Zigbee coordinator; mature device support |
| zwave-js-ui | `zwavejs/zwave-js-ui` | `zwave` | Owns the Z-Wave stick; S2 security |
| matter-server | OHF Matter Server (matter.js) image | `matter` | Owns Matter fabric; needs host networking + IPv6 |
| go2rtc | `alexxit/go2rtc` | `cameras` | RTSP to WebRTC transcoding |
| script-runner | `ghcr.io/<org>/cave-script-runner` (PowerShell 7, Python 3 and Bash on a slim Debian base) | `scripts` | Sandboxes user scripts |
| docker-proxy | `tecnativa/docker-socket-proxy` | `docker` | Read-only, filtered Docker API |
| postgres | `postgres:17` | `postgres` | Optional; SQLite is default |

**compose.yaml (excerpt)**

```yaml
services:
  cave-core:
    image: ghcr.io/<org>/cave-core:stable
    network_mode: host            # needed for mDNS, SSDP and Wake-on-LAN discovery
    volumes:
      - ./config:/config
      - ./data:/data
    environment:
      CAVE_TZ: America/Los_Angeles
    restart: unless-stopped

  zigbee2mqtt:
    image: koenkk/zigbee2mqtt
    profiles: [zigbee]
    volumes: ["./sidecars/z2m:/app/data"]
    devices:
      - /dev/serial/by-id/usb-ITead_Sonoff_Zigbee_3.0_USB_Dongle_Plus-if00:/dev/ttyACM0
    depends_on: [mosquitto]
    restart: unless-stopped

  script-runner:
    image: ghcr.io/<org>/cave-script-runner:stable   # pwsh 7, python3, bash
    profiles: [scripts]
    volumes: ["./config/scripts:/scripts:ro"]
    tmpfs: [/tmp, /work]          # scratch space and per-script Python venvs
    read_only: true
    cap_drop: [ALL]
    mem_limit: 512m
    cpus: 1.0
    restart: unless-stopped
```

The CAVE-host target needs no container: an Admin runs `cave host-scripts enable`, which creates the `cave-scripts` user on the host and installs CAVE's SSH key for it.

**Path B: native packages (no Docker).** The CAVE apt repository ships `cave-core` and `cave-script-runner`; everything else comes from Debian's archive or the upstream project's own release. The setup wizard installs only the parts you pick.

| Component | Source on Debian 13 | Runs as |
| --- | --- | --- |
| cave-core (API, console, automation engine, integration hosts) | CAVE apt repo; Debian's Python 3 with the app in a venv under `/opt/cave` | `cave.service`, user `cave` |
| Mosquitto | Debian package `mosquitto` | `mosquitto.service` |
| Reverse proxy and TLS | Debian package `nginx` (or `caddy`) | `nginx.service` |
| PostgreSQL (optional) | Debian package `postgresql` | `postgresql.service` |
| Zigbee2MQTT | Upstream release on Debian's `nodejs` | `zigbee2mqtt.service`, user in the `dialout` group |
| Z-Wave JS UI | Upstream release (Node.js) | `zwave-js-ui.service`, `dialout` group |
| Matter Server | Upstream release (Node.js) | `matter-server.service` |
| go2rtc | Single upstream binary | `go2rtc.service` |
| Script runner | CAVE apt repo; `python3` and `bash` from Debian; PowerShell 7 from [Microsoft's Debian repository](https://learn.microsoft.com/en-us/powershell/scripting/install/install-debian) on amd64, or the release archive on arm64 | `cave-script-runner.service`, sandboxed |

The script runner gets the same isolation as the container, from systemd:

```ini
# /etc/systemd/system/cave-script-runner.service (excerpt)
[Service]
ExecStart=/opt/cave/bin/cave-script-runner
DynamicUser=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
NoNewPrivileges=yes
ReadOnlyPaths=/etc/cave/scripts
StateDirectory=cave-runner
MemoryMax=512M
CPUQuota=100%
```

The CAVE-host script target works the same on both paths: SSH to localhost as the restricted `cave-scripts` user.

**Hardware targets**

- Minimum: 4-core amd64 or arm64, 4 GB RAM, SSD (no SD cards for the database).
- Recommended: Intel N100-class mini PC with Debian 13 minimal, or a Raspberry Pi 5 (8 GB) with NVMe running Raspberry Pi OS Lite, which is Debian-based. Use 8 GB or more if running cameras.
- Proxmox VM or LXC: start from a Debian 13 template; pass USB radios through by ID and give the VM a bridged NIC for discovery.
- Synology Container Manager: Path A only; USB radios work better as network coordinators (Ethernet Zigbee) there.

**Files:** `config` (YAML, scripts, themes — back up and put in Git) and `data` (database, secrets, history — back up, never commit). Docker installs keep them in `./config` and `./data`; native installs use `/etc/cave` and `/var/lib/cave`.

## Security and privacy

CAVE makes no outbound connection unless a user adds a cloud integration or turns on update checks, and every admin action is written to the audit log.

**Sign-in and roles** are covered in Navigation, sign-in and permissions, above.

**Secrets**

- Integration credentials are encrypted at rest (libsodium secretbox) with a key in `/data/.key`, never in `/config`.
- YAML references secrets with `!secret smtp_password`; the console masks them and the API never returns them.
- Diagnostics and support bundles redact tokens, emails, IPs and serial numbers.

**Network and runtime**

- HTTPS required for remote access; recommended path is your own Nginx reverse proxy, WireGuard or Tailscale.
- Webhooks use unguessable IDs, optional HMAC and rate limits.
- Docker access goes only through the filtered socket proxy; the script runner can't reach the Docker socket, the database or the /data volume.
- Signed, multi-arch images with SBOMs; Dependabot / Renovate on all lockfiles.

**Audit log** — who, what, when, from where (IP, user agent), before/after diff for config changes. Retained 365 days by default; exportable as CSV.

## Roadmap

CAVE proves local-only control in Phase 2, before building automations. Phases run in order; each must pass its gate. Dates are set once team size is known.

| Phase | What ships | Exit gate |
| --- | --- | --- |
| 0 · Foundation | Monorepo, CI, CLAUDE.md, ADRs 1–7, license review; JSON Schemas for entities, dashboards, automations | ADRs 1 and 2 approved; CI green on an empty build |
| 1 · Core platform | Registry, state machine, event bus, recorder, REST + WebSocket; sign-in, 5 roles + per-user toggles, audit log, YAML loader, dashboard-first shell | Entity created by the API shows live in the console |
| 2 · First integrations and dashboards | MQTT, Zigbee, Hue, TP-Link, ntfy, SMTP, OpenWeather, NUT, Docker; setup wizard, dashboards, Simple editors, YAML editor, themes | A Zigbee lamp toggles from a dashboard with the internet off |
| 3 · Automations | Trigger/condition/action engine, sequences, run modes, traces; script runner (PowerShell, Python, Bash), Z-Wave JS UI, visual automation builder | UPS-on-battery example passes an end-to-end test |
| 4 · Media and infrastructure | Sonos, Plex, Jellyfin, webOS, Samsung TV, Apple TV, Spotify; UniFi Network, AdGuard Home, Proxmox, Synology, Nginx | 23 integrations at Bronze tier or better |
| 5 · Energy, cloud, Matter, cameras | Enphase, EcoFlow, LG ThinQ, Apple iCloud, IFTTT; Matter Server, go2rtc cameras, energy dashboard card | All 30 integrations at Bronze tier or better |
| 6 · 1.0 release | Native .deb packages, backup and restore, upgrades, docs site, security review; public beta, translation framework, signed multi-arch images | Beta has no open data-loss or security-critical bugs |

Each phase is a milestone you can hand to Claude Code or a contributor with its gate as the acceptance test. Phase 2 is the key proof point: if a lamp can't be controlled with the internet unplugged, nothing after it matters.

## Repo layout and contributor guidance

One monorepo, one lint/test command per language, and a `CLAUDE.md` at the root so Claude Code and human contributors follow the same rules.

**Layout**

```text
cave/
├─ CLAUDE.md                  # build/test commands, conventions, "never do" list
├─ docs/
│  ├─ adr/                     # architecture decision records (0001-python-core.md …)
│  └─ integrations/            # one page per integration
├─ core/                       # Python package: cave.core
│  ├─ api/                     # FastAPI routers, WebSocket
│  ├─ registry/                # devices, entities, areas, labels
│  ├─ state/                   # state machine, event bus, recorder
│  ├─ automation/              # triggers, conditions, actions, traces
│  ├─ config/                  # YAML loader, JSON Schemas, !secret
│  └─ hosts/                   # integration-host supervisor, JSON-RPC
├─ sdk/                        # cave-sdk: base classes integrations import
├─ integrations/<domain>/      # manifest.yaml, __init__.py, config_flow.py, tests/, fixtures/
├─ console/                    # React + Fluent UI app
├─ runner-scripts/             # script runner image (pwsh, python, bash)
├─ schemas/                    # published JSON Schemas (dashboard, automation, theme)
├─ deploy/compose.yaml
├─ packaging/debian/           # .deb build files, systemd units, install.sh
└─ .github/workflows/          # lint, test, build multi-arch images, release
```

**Contribution rules**

1. Every PR passes `ruff`, `mypy --strict` (core and SDK), `pytest`, and `pnpm lint && pnpm test` for the console.
2. New integrations start at Bronze tier and must include recorded fixtures — no tests that hit real devices or clouds in CI.
3. Architecture changes need an ADR in `docs/adr/` before code.
4. Conventional Commits; semantic-release builds changelogs.
5. DCO sign-off (`git commit -s`) instead of a CLA.

**Working with Claude Code**

- Give Claude Code one milestone at a time from the Roadmap, with its exit gate as the acceptance test.
- `CLAUDE.md` lists: how to run tests, the entity/capability schema location, "never call real devices in tests", "never log secrets", and "update the JSON Schema and docs page with any YAML change".
- Ask it to write the ADR or schema first, then the code, then the tests against fixtures.
- Keep a `docs/integrations/_template.md` and an `integrations/_template/` scaffold so each new integration follows the same shape.

## Open decisions

Nine decisions should be settled as ADRs in Phase 0; the first two block Phase 1 code.

| # | Decision | Options | Recommendation |
| --- | --- | --- | --- |
| 1 | Project license | Apache-2.0 · MIT · GPL-3.0 | Apache-2.0; get a license opinion on running GPL libraries (python-kasa) in a separate process, or write a clean-room Kasa/Tapo client |
| 2 | Integration isolation | In-process (like Home Assistant) · integration hosts over JSON-RPC | Integration hosts; it's the main architectural difference from Home Assistant |
| 3 | Template language | Jinja2 sandbox · CEL · none | Jinja2 sandbox for familiarity; expose only a curated function set |
| 4 | Zigbee approach | Zigbee2MQTT only · native zigpy too | Zigbee2MQTT only for v1 |
| 5 | History storage | SQLite / PostgreSQL only · add InfluxDB or TimescaleDB | SQLite / PostgreSQL in v1; InfluxDB export as a later integration |
| 6 | Name and trademark | Keep "CAVE" · rename | Run a trademark and GitHub/PyPI/Docker Hub name check before going public |
| 7 | Governance and community | Single maintainer · core team + steering group | Start with a core team of 2–3 maintainers, `CODEOWNERS` per integration, GitHub Discussions + Matrix |
| 8 | Scripts on the CAVE host | Not allowed · SSH to localhost as a restricted user · a host agent service | SSH to localhost as `cave-scripts`, off by default; revisit a host agent only if SSH proves awkward on NAS platforms |
| 9 | Native package delivery | Signed apt repository · install script only · Debian official archive | Signed apt repository built in CI (reprepro or aptly) and hosted as static files; aim for the Debian archive after 1.0 |

## Sources

- [Getting Started with the Official UniFi API — Ubiquiti Help Center](https://help.ui.com/hc/en-us/articles/30076656117655)
- [EcoFlow integration — Gladys Assistant docs](https://gladysassistant.com/docs/integrations/external/ecoflow/)
- [ThinQ Connect Personal Access Token — LG ThinQ Developer](https://thinq.developer.lge.com/en/cloud/docs/thinq-connect/PAT-en)
- [Enphase IQ Gateway — evcc docs](https://docs.evcc.io/en/meters/enphase-iq-gateway)
- [python-kasa — GitHub](https://github.com/python-kasa/python-kasa) and its [LICENSE](https://raw.githubusercontent.com/python-kasa/python-kasa/master/LICENSE)
- [The Matter upgrade you've been waiting for — Home Assistant blog, June 2026](https://home-assistant.io/blog/2026/06/23/the-matter-upgrade-youve-been-waiting-for)
- [Debian 13 "trixie" release information](https://www.debian.org/releases/trixie/)
- [Install Docker Engine on Debian — Docker docs](https://docs.docker.com/engine/install/debian/)
- [Install PowerShell on Debian — Microsoft Learn](https://learn.microsoft.com/en-us/powershell/scripting/install/install-debian)
- [Authelia — GitHub](https://github.com/authelia/authelia) · [authentik — GitHub](https://github.com/goauthentik/authentik)
- Reference products: [Gladys Assistant](https://gladysassistant.com/) · [Home Assistant](https://www.home-assistant.io/)

Protocol details for the remaining integrations (ports, auth flows, library names) are approximate and should be confirmed on each integration's docs page in Phase 0.
