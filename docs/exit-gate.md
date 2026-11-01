# Phase 1 exit gate

The spec's gate (`docs/superpowers/specs/2026-10-25-cave-phase1-design.md`, "Exit gate for Phase 1"):

> With the internet unplugged on a Debian 13 box running the Compose stack, these four things hold.

Each item below lists the automated tests that pin it and the result of the manual check on a real box.

Run every listed test:

```bash
cd core
pytest tests/test_mqtt_discovery.py::test_z2m_light_json_schema tests/test_mqtt_bridge.py::test_toggle_uses_current_state tests/test_guards.py::test_kids_dashboard_cannot_open_garage tests/test_guards.py::test_garage_tablet_only_on_lan tests/test_guards.py::test_command_from_wan_refused_on_local_item tests/test_guards.py::test_command_route_refuses_and_does_not_call_handler tests/test_screen_auth.py::test_unenrolled_or_other_screen_refused tests/test_tokens.py::test_other_users_token_cannot_command tests/test_exit_gate.py tests/test_whatif.py::test_ups_example_whole_run tests/test_whatif.py::test_ups_example_step_two_only tests/test_whatif.py::test_zero_side_effects tests/test_script_exit_gate.py::test_powershell_script_from_a_dashboard_button
```

## 1. A Zigbee2MQTT lamp appears through MQTT discovery and toggles from an Actions dashboard

| Automated | What it pins |
| --- | --- |
| `test_mqtt_discovery.py::test_z2m_light_json_schema` | A Zigbee2MQTT light's discovery message becomes a CAVE light. |
| `test_mqtt_bridge.py::test_toggle_uses_current_state` | Toggle publishes the right command for the light's current state. |
| `test_mqtt_client.py::test_live_broker_roundtrip` (CI, real Mosquitto) | Discovery and state arrive through the Compose stack's broker. |

**On the box:** not run yet.

## 2. "Garage Door Control" holds

The setup: the dashboard is assigned only to an enrolled tablet, with "Local network only". Each of these is refused by the server:

| Refusal | Automated |
| --- | --- |
| A household member's browser | `test_exit_gate.py::test_household_browser_cannot_open_garage_dashboard` (end to end), `test_guards.py::test_command_route_refuses_and_does_not_call_handler` |
| A second, unenrolled tablet on the LAN | `test_screen_auth.py::test_unenrolled_or_other_screen_refused`, `test_guards.py::test_garage_tablet_only_on_lan` |
| The enrolled tablet's session from outside the local range | `test_guards.py::test_garage_tablet_only_on_lan`, `test_guards.py::test_command_from_wan_refused_on_local_item` |
| A raw API call with another user's token | `test_tokens.py::test_other_users_token_cannot_command` |
| A command sent through the Kids dashboard | `test_guards.py::test_kids_dashboard_cannot_open_garage` |

**On the box:** not run yet.

## 3. The UPS-on-battery automation runs in the Test Center

It runs against simulated inputs, whole and from step 2 only, with a summary of 0 changes, 0 messages, 0 scripts.

| Automated | What it pins |
| --- | --- |
| `test_whatif.py::test_ups_example_whole_run` | The whole run, with the summary. |
| `test_whatif.py::test_ups_example_step_two_only` | Starting at step 2. |
| `test_whatif.py::test_zero_side_effects` | Nothing real happens: no device, message or script. |

**On the box:** not run yet.

## 4. A PowerShell script runs from a dashboard button in the sandbox, and its result shows in the audit log

| Automated | What it pins |
| --- | --- |
| `test_script_exit_gate.py::test_powershell_script_from_a_dashboard_button` | The button runs the script through the runner, and the result is audited. |
| CI `images.yml` | PowerShell runs in the runner image on amd64 and arm64. |

**On the box:** not run yet.

## The run on a real box

These steps are done by hand, because they need real hardware: a Debian 13 machine, a Zigbee coordinator and lamp, and two tablets.

1. Install while online: `deploy/install.sh --profiles mqtt,scripts`. Pair the lamp through Zigbee2MQTT. Enroll one tablet as a screen.
2. Unplug the internet at the router (the LAN stays up). Reboot the box. `docker compose ps` should show everything running, with no downloads.
3. Walk items 1 to 4 above:
   - **Item 2:** use the second tablet, a phone hotspot for "outside the range", and `curl` with another user's token.
   - **Items 1 to 4:** record each result and the date in the section above.

| Box | Architecture | Date | Result |
| --- | --- | --- | --- |
| (not run yet) | | | |
