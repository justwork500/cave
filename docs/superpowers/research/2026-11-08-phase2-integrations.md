# Phase 2 research: 30 local integrations

Nov 8, 2026 · Input to the Phase 2 design, not a decision. The Phase 1 design asks for "a rebuilt list of 30: the easiest, most open and most popular local integrations available today, chosen by research before Phase 2 starts". This list replaces the framework's catalog.

## How the list was built

- **Popularity:** Home Assistant's opt-in analytics (`analytics.home-assistant.io/data.json`, snapshot 2026-11-08 12:49 UTC). 725,182 active installations, of which 573,903 report their integrations. Counts below are installations using each integration. This is the best public measure of what people actually run at home.
- **Local only:** the device or service must work over the home network, with no internet connection or vendor account. Cloud-only integrations are left out, as are ones whose local mode is a community add-on.
- **A device or service:** Home Assistant internals and helpers (templates, the recorder, text-to-speech and so on) are left out.
- **Already in CAVE:** MQTT, which covers Zigbee2MQTT, Tasmota and ESPHome or Shelly devices set to MQTT, and TP-Link Kasa. They're not counted again.
- **Openness:** *open* means an open standard or a published, vendor-documented local API. *Stable* means undocumented but long-lived, with a mature open-source client. *Fragile* means reverse-engineered and changed by firmware updates before.
- **Effort** is a guess. **S:** a small HTTP or UDP client. **M:** pairing, discovery or a larger protocol. **L:** a sidecar container or a radio stick.

Library licenses are checked one by one in the Phase 2 spec, the way python-kasa's GPL-3.0 led CAVE to write its own Kasa client.

## The 30, by installations

| # | Integration | Installs | What it gives a house | Openness | Effort |
|---|---|---:|---|---|---|
| 1 | Google Cast (Chromecast, Nest speakers, Cast TVs) | 292,897 | Media control, announcements | Stable | M |
| 2 | Matter (with Thread) | 239,291 | The new cross-vendor standard for lights, plugs, locks and sensors | Open | L: Matter server sidecar, Thread border router |
| 3 | UPnP / IGD (router) | 185,208 | Router traffic and uptime | Open | S |
| 4 | Printers (IPP) | 167,439 | Ink and toner levels, printer state | Open | S |
| 5 | DLNA renderers and media servers | 158,800 | Play to TVs and speakers; browse media | Open | M |
| 6 | ESPHome (native API) | 157,413 | DIY sensors, relays and displays, with live push | Open | M |
| 7 | Shelly | 145,737 | Relays, plugs, dimmers and energy meters | Open | S |
| 8 | Android TV Remote | 119,738 | Google TV and Android TV: power, apps, keys | Stable | M: pairing code |
| 9 | Samsung TVs | 98,064 | Power, source, keys | Fragile | M |
| 10 | Sonos | 93,205 | Speakers, grouping, announcements | Stable | M |
| 11 | Apple TV | 91,182 | Power, playback, apps | Stable | M: pairing |
| 12 | Philips Hue | 90,883 | Lights, scenes, motion sensors | Open | S: press the bridge button |
| 13 | HomeKit devices (HomeKit Controller) | 84,427 | HomeKit-only devices, locally, without Apple hardware | Open | L |
| 14 | System monitor (CAVE host) | 78,459 | CPU, memory, disk, temperature | Open | S |
| 15 | LG webOS TVs | 70,048 | Power, inputs, apps | Stable | M: on-screen pairing |
| 16 | Reolink cameras and doorbells | 64,315 | Motion, person and doorbell events, snapshots | Open | M |
| 17 | Synology NAS | 52,585 | Volumes, disks, temperatures, shutdown | Open | S |
| 18 | Wake on LAN and ping | 52,660 / 46,163 | Wake PCs, see what's online | Open | S |
| 19 | FRITZ!Box | 50,539 | Router, presence, call events | Open (TR-064) | M |
| 20 | Brother printers | 49,685 | Toner, drum and page counts | Open (SNMP) | S |
| 21 | Z-Wave (Z-Wave JS) | 46,707 | Locks, sensors and switches on Z-Wave | Open | L: Z-Wave JS sidecar and USB stick |
| 22 | UniFi Network | 43,665 | Presence by Wi-Fi client, block or allow devices | Stable | M |
| 23 | WLED | 34,462 | LED strips: color, effects, presets | Open | S |
| 24 | Broadlink | 34,023 | Infrared and RF remotes for air conditioners, TVs and fans | Stable | M |
| 25 | ONVIF cameras | 29,901 | Camera events and snapshots from most IP cameras | Open | M (live video needs go2rtc) |
| 26 | NUT (UPS) | 26,005 | UPS battery, load, on-battery events | Open | S |
| 27 | AdGuard Home | 24,268 | DNS filtering on or off, stats | Open | S |
| 28 | Fully Kiosk Browser | 24,150 | Wall tablets: screen on or off, brightness, motion, battery | Open | S |
| 29 | WiZ | 23,473 | Wi-Fi bulbs and plugs | Stable | S |
| 30 | HomeWizard Energy | 20,721 | Smart meter, sockets, water meter | Open | S |

**Next in line** if any of the 30 drop out: Plex (19,883), Modbus (19,143), Denon HEOS (18,420), Ecowitt weather stations (15,908), Govee local LAN (15,763), Lutron Caséta (13,628).

## Notes for the Phase 2 design

- **Fit with what CAVE already has.** NUT feeds the UPS-on-battery example straight from the UPS, without MQTT in the middle. Fully Kiosk fits CAVE's screens (wall tablets). System monitor, Synology and Wake on LAN serve the homelab side the framework describes.
- **The framework's Phase 2 gate** was "a Zigbee lamp toggles from a dashboard with the internet off", and Phase 1 already passed it through Zigbee2MQTT. ZHA (145,620 installs, Zigbee without MQTT) is left out for that reason.
- **Big but not local, so left out:** Tuya (169,186), SmartThings, Roborock, Ring, Nest, Netatmo, LG ThinQ, Home Connect and Spotify all need the vendor's cloud. Govee BLE, SwitchBot, Xiaomi BLE and BTHome are local, but they need a Bluetooth adapter; they could make one "Bluetooth sensors" item if CAVE adds Bluetooth.
- **Needs the internet by nature:** weather (Met.no, 479,240 installs, is Home Assistant's default; Open-Meteo, 19,871) and forecasts such as Forecast.Solar. They break the "works offline" goal but would help automations, so whether CAVE has any is a design question.
- **Already promised for Phase 2 and not counted here:** ntfy and SMTP notification targets (Phase 1 design, "Notifications in Phase 1"), and the setup-wizard network scan, which can build on the Kasa LAN scan.
- **Sidecars:** Matter and Z-Wave each need a separately maintained server container, plus hardware (a Thread border router, a Z-Wave stick). They are the most work and the most valuable for locks and the newest devices.
- **Fragile ones:** Samsung TV pairing and protocol have changed with TV firmware before. Ship it with that warning, or later.

## Sources

- Home Assistant analytics, raw data: https://analytics.home-assistant.io/data.json (snapshot 2026-11-08)
- Home Assistant analytics site: https://analytics.home-assistant.io/
- Home Assistant IoT classes (local push, local polling, cloud): https://www.home-assistant.io/integrations/ (integration catalog filters)
