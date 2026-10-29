# Automations, routines and dashboards

Everything here is a YAML file under `config/`, so you can keep it in Git and edit it with any editor. The console's editors (coming in a later phase) write the same files.

| What | Folder | Item in Users and permissions |
| --- | --- | --- |
| Automation ("when this happens, do that") | `config/automations/<id>.yaml` | `automation:<id>` |
| Routine (a reusable list of steps) | `config/sequences/<id>.yaml` | `sequence:<id>` |
| Dashboard | `config/dashboards/<slug>.yaml` | `dashboard:<slug>` |

The file name is the ID: lowercase letters, digits, `-` and `_`. For automations and routines, the `id:` inside must match the file name.

**Get autocompletion:** point your editor's YAML extension at the JSON Schemas in [`schemas/`](../schemas) (`automation.json`, `sequence.json`, `dashboard.json`). CAVE also serves them at `/api/v1/schemas/<name>.json`.

**Mistakes show the file and line**, for example `kids-off.yaml:11: automation.actions[0].comand: Extra inputs are not permitted`. A file that doesn't load is listed at `GET /api/v1/config/errors`, and stops running until it's fixed. CAVE itself keeps running.

**Files never change who can use what.** A new file starts as Restricted with no one assigned. Access is set in Users and permissions and stored in CAVE's database. Every change to a file is written to the audit log.

## An example

```yaml
# config/automations/ups-on-battery.yaml
automation:
  id: ups-on-battery
  name: UPS on battery — alert and shut down lab
  mode: single
  triggers:
    - type: state
      entity: binary_sensor.ups_on_battery
      to: "on"
      for: "00:02:00"
  conditions:
    - type: numeric_state
      entity: sensor.ups_battery_runtime_min
      below: 15
  actions:
    - type: notify
      title: Power outage
      message: "UPS on battery. {{ states('sensor.ups_battery_runtime_min') }} min left."
    - type: sequence
      ref: sequence.lab_safe_shutdown
      with:
        grace_seconds: 120
```

## Triggers

| Type | Fires when | Example |
| --- | --- | --- |
| `state` | a device changes, optionally `from` / `to` a value, optionally after holding it `for` a while | `entity: binary_sensor.door`, `to: "on"`, `for: "00:05:00"` |
| `numeric_state` | a value crosses into a range (`above` / `below`); not again while it stays there | `entity: sensor.temp`, `above: 25` |
| `time` | at a local time | `at: "07:30"` |
| `time_pattern` | on a repeating minute or hour | `minutes: "/15"` |
| `startup` | CAVE starts | |

**Coming later:** sunrise and sunset, incoming webhooks, raw MQTT topics, device buttons and zones. Until then, use an MQTT device's own entity with a `state` trigger.

## Conditions

`state` (with a value or a list of values), `numeric_state` (`above` / `below`), `time` (`after`, `before`, `weekdays: [mon, tue, …]`; a window like 22:00–06:00 crosses midnight), `template` (true when it renders `true`, `yes`, `on` or `1`), and `and` / `or` / `not` with nested `conditions`.

## Actions

| Type | Does |
| --- | --- |
| `call` | sends a command: `target: light.kitchen`, `command: turn_on`, `args: {brightness: 120}` |
| `notify` | puts a message in the console's bell. `targets: [user:sam]`, or leave it out to notify whoever last saved the automation (or every Admin) |
| `delay` | waits: `duration: "00:00:30"` |
| `wait_for` | waits for a device to reach a value: `entity`, `to`, `timeout`, `on_timeout: stop` or `continue` |
| `choose` | runs the first `option` whose `conditions` pass, otherwise `default` |
| `repeat` | `count: 3`, or `while:` / `until:` conditions (1,000 times at most) |
| `sequence` | runs a routine: `ref: sequence.<id>`, `with: {field: value}` |
| `script` | runs a PowerShell, Python or Bash script (arrives with the script runner) and keeps its JSON result in `result_var` |
| `set_variable` | `name`, `value` |
| `stop` | ends the run, optionally with a `reason` |
| `mqtt_publish` | `topic`, `payload`, `retain` |

Durations accept `"HH:MM:SS"`, `"MM:SS"` or seconds, up to 24 hours. Steps can nest up to 8 levels deep, and one run can take at most 10,000 steps in all, counting every repeat and routine. A routine can be running at most 10 times at once. Templates are checked when the file is loaded or saved, so a mistake shows its line straight away, not when the automation first runs.

## Run modes

What happens when an automation triggers while it's still running:

| `mode` | Behaviour |
| --- | --- |
| `single` (default) | the new trigger is ignored |
| `restart` | the running one is stopped and a new run starts |
| `queued` | runs one after another, keeping up to `max` (default 10) waiting |
| `parallel` | runs side by side, up to `max` at once |

Every run leaves a step-by-step **trace**. CAVE keeps the last 20 per automation, at `GET /api/v1/automations/<id>/traces`.

## Templates

Text fields can use `{{ … }}` to read values: `states('sensor.x')`, `is_state('lock.front', 'locked')`, `state_attr('sensor.x', 'unit_of_measurement')`, `now()`, plus variables such as `trigger` and a script's `result_var`. Templates can compare, use `if` / `else` and do arithmetic. They can also use the filters `float`, `int`, `round`, `default`, `lower`, `upper`, `trim`, `replace`, `length`, `first`, `last`, `abs`, `string` and `tojson`. Loops and other function calls aren't allowed.

**Name devices directly.** Write `states('cover.garage_door')`, not `states(some_variable)`. Only Admins may save templates that build device names on the fly, because CAVE can't otherwise tell which devices they read.

## Who can save what

You can save, change, delete, read or test an automation, routine or dashboard only if you could already control **every device it names**, and use every routine or automation it runs. This includes devices it only reads in a message. Otherwise anyone with the Automations section could write "open the garage" or "tell me whether the garage is open" and get around the dashboards that decide who controls it. Admins aren't limited.

Running an automation from a dashboard button only needs that automation assigned to you. The automation acts on its own author's behalf, so assigning "Close garage" lets someone close the garage through it, and nothing more.

## The Test Center

Rehearse an automation without touching anything, like PowerShell's `-WhatIf`. `POST /api/v1/test-center/run` takes:

- the automation or routine (`kind`, `id`), or an unsaved draft (`yaml`)
- the simulated `trigger` and device `states`, for example `{"sensor.ups_battery_runtime_min": "12"}`
- optionally `start_at: "actions[1]"`, to test only from the step you're working on
- `script_samples`: what each script would have returned

It runs the real automation logic, and replaces every action with a "What if:" line: commands aren't sent, messages aren't delivered, scripts don't run, and waits and delays finish at once. The result always ends with **"0 devices changed, 0 messages sent, 0 scripts run."**
