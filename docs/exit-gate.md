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

**On the box (2026-11-01):** partly.
- `test_live_broker_roundtrip` passed against the box's own Mosquitto: a Zigbee2MQTT light's discovery and state came through the real broker, with CAVE signed in as `cave`.
- Mosquitto refused an anonymous client.
- **Still to do:** a physical Zigbee lamp through a real coordinator.

## 2. "Garage Door Control" holds

The setup: the dashboard is assigned only to an enrolled tablet, with "Local network only". Each of these is refused by the server:

| Refusal | Automated |
| --- | --- |
| A household member's browser | `test_exit_gate.py::test_household_browser_cannot_open_garage_dashboard` (end to end), `test_guards.py::test_command_route_refuses_and_does_not_call_handler` |
| A second, unenrolled tablet on the LAN | `test_screen_auth.py::test_unenrolled_or_other_screen_refused`, `test_guards.py::test_garage_tablet_only_on_lan` |
| The enrolled tablet's session from outside the local range | `test_guards.py::test_garage_tablet_only_on_lan`, `test_guards.py::test_command_from_wan_refused_on_local_item` |
| A raw API call with another user's token | `test_tokens.py::test_other_users_token_cannot_command` |
| A command sent through the Kids dashboard | `test_guards.py::test_kids_dashboard_cannot_open_garage` |

**On the box:** not run yet. It needs two tablets, one enrolled as a screen, and a phone hotspot for "outside the range".

## 3. The UPS-on-battery automation runs in the Test Center

It runs against simulated inputs, whole and from step 2 only, with a summary of 0 changes, 0 messages, 0 scripts.

| Automated | What it pins |
| --- | --- |
| `test_whatif.py::test_ups_example_whole_run` | The whole run, with the summary. |
| `test_whatif.py::test_ups_example_step_two_only` | Starting at step 2. |
| `test_whatif.py::test_zero_side_effects` | Nothing real happens: no device, message or script. |

**On the box (2026-11-01):** passed.
- The UPS automation, its routine and `Stop-LabHosts.ps1` were saved through the API.
- The Test Center ran it whole and from step 2 (`actions[1]`). Every acting step was a "What if", and the summary read "Done. 0 devices changed, 0 messages sent, 0 scripts run."
- The audit log gained no `script.run`.

## 4. A PowerShell script runs from a dashboard button in the sandbox, and its result shows in the audit log

| Automated | What it pins |
| --- | --- |
| `test_script_exit_gate.py::test_powershell_script_from_a_dashboard_button` | The button runs the script through the runner, and the result is audited. |
| CI `images.yml` | PowerShell runs in the runner image on amd64 and arm64. |

**On the box (2026-11-01):** passed.
- A "Say hello" button on a dashboard ran a routine, which ran `Gate-Hello.ps1` in the sandbox.
- The audit log recorded `script.run` with outcome `finished`, exit code 0, and the result `{"status": "hello from PowerShell 7.6.9", "ok": true}`.
- Checked in the same container: scripts run as uid 10002. They can't read the runner token or its environment, and can't write the scripts folder.

## The run on a real box

These steps are done by hand, because they need real hardware: a Debian 13 machine, a Zigbee coordinator and lamp, and two tablets.

1. Install while online: `deploy/install.sh --profiles mqtt,scripts`. Pair the lamp through Zigbee2MQTT. Enroll one tablet as a screen.
2. Unplug the internet at the router (the LAN stays up). Reboot the box. `docker compose ps` should show everything running, with no downloads.
3. Walk items 1 to 4 above:
   - **Item 2:** use the second tablet, a phone hotspot for "outside the range", and `curl` with another user's token.
   - **Items 1 to 4:** record each result and the date in the section above.

| Box | Architecture | Date | Result |
| --- | --- | --- | --- |
| A test VM: Debian 13.7, amd64, 2 cores, 4 GB, 20 GB | amd64 | 2026-11-01 | Items 3 and 4 passed. Item 1 passed through the real broker; the physical lamp is still to do. Item 2 is still to do (needs tablets). |

### What that run checked

1. **Install:**
   - `docker.io`, `docker-compose` and `docker-buildx` from Debian's packages, then `deploy/install.sh --profiles mqtt,scripts`
   - all three containers up, CAVE healthy, the setup code and fingerprint printed
   - `.env` held the real LAN range (a /24)
   - ownership as designed: `data`/`config` 10001, Mosquitto 1883, secrets `0400`
2. **`deploy/smoke.py`:** all ten checks passed, including:
   - setup with the printed code and an authenticator
   - saving a file through the API
   - the runner not reachable from the host
   - Mosquitto refusing anonymous clients
   - no secret in `docker compose config` or `docker inspect`
3. **Restart:** after `docker compose restart cave`, the owner still signs in.
4. **Upgrade:** pull, then `deploy/install.sh` again. It kept `.env` and the secrets, rebuilt, and restarted.
5. **Offline:** the default route was removed (netplan `use-routes: false`), so neither the registry nor the internet could be reached. One leftover host route to the DHCP-provided DNS server stayed up. After a reboot:
   - the stack came back by itself, healthy
   - `docker compose up -d` succeeded with no downloads
   - the owner signed in
   - a PowerShell script ran from its button

The run found three bugs that no test here could. Each is fixed with a regression test (see `fix(deploy)` and `fix(runner)` in the history):
- the installer's `chmod` ran as the normal user on a file it had just handed to Mosquitto's uid
- uvicorn picked uvloop in the image, whose subprocess call refuses `user=`, so every script run failed
- the review's fixes for buffered logs and the runner's token permission were confirmed in the real container
