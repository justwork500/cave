# MQTT

MQTT is how most do-it-yourself and Zigbee devices talk. CAVE connects to an MQTT broker (Mosquitto) and **finds devices by itself**, as long as they announce themselves with the widely used MQTT discovery messages. Zigbee2MQTT, Tasmota, Shelly and ESPHome all do this. Everything stays on your network.

## Turn it on

Create `config/mqtt.yaml`:

```yaml
broker:
  host: mosquitto      # or the broker's IP address
  port: 1883
  username: cave
```

Set the broker password in the environment variable `CAVE_MQTT_PASSWORD`. It never goes in a config file, because config files are meant to be kept in Git. Then restart CAVE.

The connection status, the device count and anything CAVE couldn't use are shown at `GET /api/v1/system/mqtt`, and later on the console's Home page. If the broker is down, CAVE keeps running and retries, waiting 1, 2, 4 … up to 60 seconds between tries.

## Make your devices announce themselves

| Software | Setting |
| --- | --- |
| Zigbee2MQTT | `homeassistant: enabled: true` in its `configuration.yaml` (the default) |
| Tasmota | `SetOption19 0` (turns on discovery messages in recent versions) |
| Shelly (Gen2+) | Settings › MQTT › enable, with "Generic status update" and discovery on |
| ESPHome | an `mqtt:` block with `discovery: true` (the default) |

CAVE listens on the discovery prefix `homeassistant/`, the name these tools use for the shared message format. Change it with `discovery_prefix:` in `mqtt.yaml` if yours differs.

## What CAVE understands

| Type | Shows | Accepts |
| --- | --- | --- |
| Light | on / off, brightness | `turn_on` (optional `brightness` 0–255), `turn_off`, `toggle` |
| Switch | on / off | `turn_on`, `turn_off`, `toggle` |
| Sensor | its value, with unit | — |
| Binary sensor (door, motion…) | on / off | — |
| Cover (blinds, garage doors) | open / closed / opening / closing | `open`, `close`, `stop` |
| Lock | locked / unlocked | `lock`, `unlock` |
| Button | — | `press` |

A device that goes offline shows **unavailable**. Colour lights work, but only on/off and brightness for now. Anything CAVE doesn't support yet (thermostats, fans, …) is listed under `unsupported` in the MQTT status, with the reason, instead of half-working.

## New devices are Admin-only until you add them to a dashboard

Anything that can reach your broker can announce a "device". So a newly found device starts out **Admin-only**. Household members, screens and API tokens get control only once an Admin puts it on a dashboard or in an action they're assigned to. Keep the broker password private, and keep anonymous access off (the shipped Mosquitto config does).

Each device's ID (for example `light.kitchen_lamp`) is fixed the first time CAVE sees it and never changes after that, even if you rename the device. Your automations and dashboards keep working.

## Devices that don't announce themselves

Describe them in `mqtt.yaml`, using the same keys as the discovery format:

```yaml
entities:
  - component: switch
    unique_id: garage_heater
    name: Garage heater
    state_topic: garage/heater/state
    command_topic: garage/heater/set
    payload_on: "1"
    payload_off: "0"
```

Typos are rejected with the exact key, for example `mqtt.yaml: entities[0].colour: Extra inputs are not permitted`, and MQTT stays off until the file is fixed. Wildcards (`+`, `#`) aren't allowed in topics CAVE publishes to.

## Safety limits

Messages from devices are treated as untrusted:
- configs are capped at 64 KiB and state messages at 256 KiB
- value templates run in a sandbox, are capped at 2,000 characters, and can't build huge strings or numbers
- CAVE never publishes to a wildcard topic
- at most 5,000 MQTT devices
