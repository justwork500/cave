# CAVE Phase 2 design: first integrations

Nov 8, 2026 · Status: approved by the owner, Nov 8, 2026

Builds on the [Phase 1 design](2026-10-25-cave-phase1-design.md), which still holds where this document says nothing. Input: [Phase 2 research](../research/2026-11-08-phase2-integrations.md), the list of 30 local integrations ranked by real use.

## Intent and the why

Phase 1 proved how CAVE runs a house: access control, the admin console, scripts, the Test Center and plain dashboards. It reaches devices only through MQTT and Kasa. Phase 2 makes CAVE useful in an ordinary home by adding the integrations people actually own, starting with the owner's own devices and the ones CAVE's own features lean on.

Local stays the priority. Cloud services are not banned: some devices have no other way in. CAVE will support them later, clearly labeled as cloud and kept private by default. Phase 2 builds those safeguards, so the first cloud integration lands on rules that already exist instead of making them up.

## Decided in conversation

These are the owner's decisions:

- **Local integrations come first.** Cloud integrations follow later, both cloud-only ones and cloud versions of devices that also work locally.
- **Cloud integrations must be labeled as cloud everywhere they appear, and privacy stays a priority.**
- **The list is the research's 30, plus the owner's Sony Bravia TV and IQAir AirVisual Pro.** It's built in batches. Batch 1 is below; it was proposed and accepted as is.
- **Phase 2 is the ten local integrations of batch 1. Later batches follow from there.** The cloud safeguards are written down here and built together with the first cloud integration, not before. That's this document's reading of the owner's answer "start with the top ten integrations local first".
- **NUT:** the owner already runs a UPS server on Proxmox, so CAVE connects to an existing NUT server rather than shipping one. The owner's UPS has failed and there's none on site, so the exit gate simulates one (see below).
- **ntfy is optional.** CAVE either uses an existing ntfy server or runs one as an optional add-on. The owner's phones are an iPhone and an iPad; there's no Android device to test with.
- **Deferred:** LG ThinQ (the owner's washer and dryer, cloud only) and Chamberlain myQ (the owner's garage doors). Chamberlain has blocked third-party access since November 2023. The usual local fix is a ratgdo board, which already works with CAVE through MQTT, so myQ needs no integration of its own. The owner will decide on both later.

## Goals, non-goals, anti-goals

**Goals for Phase 2**

- The ten batch 1 integrations work end to end: found or added from **Devices → Add device**, shown as plain-language entities, usable on dashboards, in automations and in the Test Center, and covered by access control exactly like today's devices.
- Notifications reach phones and inboxes through ntfy and email (SMTP), not only the console bell.
- The setup wizard can scan the network and offer the devices it finds.
- The cloud safeguards are specified, ready to build with the first cloud integration.
- Everything above works with the internet unplugged.

**Non-goals for Phase 2** (later batches or phases)

- Batches 2 and later of the list, including Matter and Z-Wave, which need sidecar servers and radios.
- Any cloud integration, LG ThinQ included.
- Live camera video (go2rtc), history charts, energy dashboards.
- A plugin store or third-party integrations loaded at runtime.

**Anti-goals** (would make Phase 2 a failure even if it works)

- CAVE itself needing the internet. A cloud service being down may stop that vendor's devices, never CAVE.
- A device reachable through an integration without going through CAVE's access checks. Every command goes through `can_control`, like MQTT and Kasa today.
- Credentials stored in plain text, or written to logs.
- Working around a vendor's block on third-party access. That's why myQ isn't here.
- Using a GPL library inside the core. Check each library's license first; where one is GPL, write CAVE's own client, as for Kasa.

## Constraints

- Phase 1's stack, install method (Debian 13, Docker Compose) and Apache-2.0 license.
- **Tests never touch real devices or the network** (`CLAUDE.md`). Each integration ships with recorded or fake device replies.
- **Integration settings live in the database, not in `/config` files.** That covers added devices, pairing keys and addresses, as Kasa does today. Settings in `/config` stay limited to things people write by hand (dashboards, automations, scripts, `mqtt.yaml`).
- Every add, remove or credential change is written to the audit log, with old and new values and with secrets masked.

## Batch 1

| Integration | Why it's in batch 1 | What it becomes in CAVE | How CAVE reaches it |
|---|---|---|---|
| **Apple TV** | Owner's device | `media_player`: power, play/pause, volume where supported, app launch | Local, one-time pairing code shown on the TV |
| **Sony Bravia TV** | Owner's device | `media_player`: power, input, volume, app launch | Local REST API ("IP control"), pre-shared key set on the TV |
| **IQAir AirVisual Pro** | Owner's device | `sensor`s: AQI, PM2.5, CO₂, temperature, humidity, battery | Local file share on the unit, with the password printed on it |
| **NUT** (UPS) | Feeds the UPS-on-battery example directly | `sensor`s and a `binary_sensor` for on battery | A client to an existing NUT server (`upsd`, TCP port 3493) on the LAN. CAVE doesn't ship a NUT server. If the owner's Proxmox UPS server is a web front end for NUT, CAVE connects to the `upsd` behind it; confirm when building. |
| **Fully Kiosk Browser** | Runs CAVE's wall tablets | Screen on/off (`switch`), brightness, battery and motion (`sensor`/`binary_sensor`) | The app's documented local REST API, with its password |
| **System monitor** | The CAVE host itself | `sensor`s: CPU, memory, disk, temperature, uptime | Read inside the core, no network |
| **Shelly** | Popular, open, easy | `switch`, `light`, energy `sensor`s | Shelly's documented local HTTP/RPC API |
| **Philips Hue** | Popular, open | `light`s (on/off, brightness, color), motion and other `sensor`s | Hue bridge local API, after pressing the bridge button |
| **WLED** | Popular, open, easy | `light`: on/off, brightness, color, presets | WLED's documented JSON API |
| **ESPHome** (native API) | Popular, open | Whatever the device exposes, mapped to existing capabilities | ESPHome native API with its encryption key |

Each integration also gets a page in `docs/integrations/`, written like `kasa.md`: how to add it, what CAVE stores, what works, and what to do if something's wrong.

## How an integration fits in (builder's call, within these rules)

This repeats the Kasa pattern rather than inventing a new one:

- **One module per integration** under `core/cave/integrations/<name>/`, with a service the app starts and stops, like `KasaService`.
- **Entities through the state machine**, using existing capabilities where they fit. `media_player` needs a defined command set (power, play, pause, volume, source or app). Fully Kiosk brightness and WLED presets may need a numeric or choice control, so add the smallest new capability that fits.
- **Adding devices from Devices → Add device.** One panel lists every integration. Each one either scans for devices (as Kasa does) or asks for an address, then runs its pairing step: a PIN, a pre-shared key, a bridge button, an encryption key or a password.
- **Stable identity:** a device's MAC address or serial number, never its IP address, so a new address doesn't create a duplicate.
- **Not responding:** a device that stops answering reads as unavailable, as Kasa and MQTT do, and comes back on its own.

## Credentials (builder's call)

Batch 1 is the first time CAVE must keep secrets it has to read back: Hue app keys, Sony pre-shared keys, Fully Kiosk and AirVisual passwords, ESPHome encryption keys, SMTP passwords and ntfy tokens. They go in the database **encrypted with a host key**, a file the installer creates in `secrets/` next to the existing ones. They're never logged and never sent back to the browser. A form shows that a value is set, not what it is. This brings forward part of the roadmap's "Secrets storage" item; TOTP secrets can move to the same key at the same time.

## Notifications

- **ntfy (optional)**: a notify target per ntfy topic, on any server URL, with an optional access token. Two ways to have a server: point CAVE at an existing ntfy server, or turn on an optional `ntfy` Compose profile that runs a pinned ntfy image next to CAVE, the way the `mqtt` profile runs Mosquitto. The installer asks, and the profile is off by default.
- **iPhone and iPad delivery.** Apple only allows instant notifications through its push service. A self-hosted ntfy server reaches it through ntfy.sh, which sees the topic name and a message ID, never the message text. With the internet unplugged, or with that relay off, the iOS app still gets the message the next time it opens or fetches, just not instantly. The add-on ships with the relay **off**. Turning it on is the first thing in CAVE labeled **Cloud**, following the safeguards below: an Admin turns it on, sees what leaves the house, and the change is audited.
- **Email (SMTP)**: server, port, TLS mode, sign-in and sender, plus the recipient addresses on each target.
- **Recipients belong to the target (builder's call).** An Admin makes each target, such as `notify.ntfy_family` or `notify.email_owner`, with its own topic or addresses. `user:<name>` targets keep meaning the console bell, as in Phase 1. Users get no email field in Phase 2.
- **Access is unchanged (builder's call).** Any automation author may use any target, as with `notify.cave` today. Targets appear in the sentence builder's notify choices.
- Automations use them the way they use `notify.cave` today. The Test Center records them as "would send", never sends.

## Network scan in the setup wizard

The setup wizard gains a step: **Find devices**. It scans the local ranges, using the same /22 limit as the Kasa scan, and lists what it recognizes from batch 1 and Kasa.

**Discovery probes addresses directly (builder's call).** The core stays on Compose's bridge network, so Phase 1's runner network, trusted-proxy setup and "Local network only" behaviour don't change. Multicast mDNS and SSDP don't cross that bridge, so each integration probes addresses itself: HTTP checks for Hue, Shelly, WLED and Fully Kiosk, a TCP check on port 6053 for ESPHome, a unicast DNS-SD query to port 5353 for Apple TV, and the Sony REST endpoint. Anything not found can be added by address. Host networking was the alternative; it was rejected because it changes how the core sees client addresses. Each device links to its add step. It never adds anything by itself. The same scan backs **Add device** on the Devices page.

## Cloud safeguards (built with the first cloud integration)

No cloud integration ships in Phase 2. These rules are the contract the first one is built to, LG ThinQ most likely. The ntfy add-on's iOS relay is the one exception in Phase 2: it follows rules 1, 2, 3 and 7 as a single setting, without the container.

1. **Labeled everywhere.** A cloud integration, its devices and any dashboard tile that controls one carry a visible **Cloud** mark, with the vendor's name on hover or long-press.
2. **Off by default.** Only an Admin can turn one on.
3. **Consent before turning it on.** A screen says what leaves the house (commands, device states, account details) and to which company, and the Admin confirms it.
4. **Kept in its own container.** Cloud integrations run in a separate **cloud host** container that can reach only that vendor's domains. It never reaches the database or `/data` directly. It talks to the core over a local connection, the way the script runner does.
5. **Prefer local.** When a device works both ways, CAVE uses the local route and labels a cloud fallback as cloud.
6. **One "Local only" switch** in System turns every cloud integration off at once.
7. **Audited.** Turning a cloud integration on or off, and accepting its consent screen, are written to the audit log.
8. **Fails alone.** A cloud integration being down marks its devices unavailable and nothing else.

## Access and the Test Center

Nothing new in the access model. New entities are controlled only through items that hold them, exactly as in Phase 1. The Test Center treats every batch 1 command as a side effect: simulated and reported, never sent. Its summary counts devices changed and messages sent, and both stay 0.

## Exit gate for Phase 2

With the internet unplugged on the Debian 13 Compose stack:

1. The setup wizard's **Find devices** step lists a Hue bridge, a Shelly device and a WLED strip on the LAN, and each one can be added from there. An Apple TV is either listed or added by its address.
2. From an assigned dashboard: a Hue light and a Shelly relay toggle, a WLED preset applies, and an Apple TV and a Sony Bravia pause and resume.
3. The UPS-on-battery automation is triggered by NUT, not MQTT. There's no UPS on site, so a NUT server runs NUT's `dummy-ups` driver, and switching its status to on battery triggers the automation. The notification reaches the local ntfy server (the add-on) and shows in ntfy's web app on the LAN, and in the iPhone app the next time it fetches. With the relay off and the internet unplugged, iPhone delivery isn't instant, and the gate doesn't require it. In the Test Center the automation reports 0 changes and 0 messages.
4. AirVisual Pro readings and the CAVE host's CPU and disk show on a dashboard.
5. A household member without access to a TV's item is refused by the server when sending it a command, as the Phase 1 gate does for the garage door.
6. The ntfy add-on's iOS relay is off by default, labeled **Cloud** when shown, and turning it on is audited.

## Later batches (outline only)

- **Batch 2:** the rest of the 30 that need no sidecar, in order of installs. Google Cast, UPnP router stats, printers (IPP and Brother), DLNA, Android TV Remote, Sonos, LG webOS, Reolink, Synology, Wake on LAN and ping, FRITZ!Box, UniFi Network, Broadlink, ONVIF events, AdGuard Home, WiZ, HomeWizard. Samsung TVs come with a warning that firmware updates have broken them before.
- **Batch 3:** Matter (with Thread) and Z-Wave JS, each with its sidecar container, and HomeKit devices.
- **First cloud integration:** LG ThinQ, when the owner picks it back up, built on the safeguards above.

## Left to the builder

- Library choice per integration, after its license check. Where no suitable non-GPL library exists, write a client.
- Exact entity names, command sets and polling intervals. Prefer push where the device offers it (Hue events, ESPHome, Shelly).
- Database schema for integrations, devices and encrypted credentials.
- How the cloud host container is wired and how its outbound traffic is limited.
- The order batch 1 is built in. Suggested: shared groundwork (credentials, the add-device panel, `media_player`) first, then the easy ones, then the TVs.
