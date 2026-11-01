# CAVE Phase 1, Plan 7: Install, Compose and the Exit Gate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A person installs CAVE on Debian 13 (amd64 or arm64) with one script and Docker Compose, then runs it with the internet unplugged. Phase 1's exit gate is checked on a real box.

**Architecture:**
- **Images:** two built from this repo, `cave-core` (the console is built in a Node stage, then copied into the Python image) and `cave-script-runner`. Mosquitto uses the upstream image, pinned by digest.
- **`compose.yaml`:** at the repo root, with profiles `mqtt` and `scripts`. The runner sits on an internal network that only `cave` shares. Secrets reach containers as files, never as environment values.
- **`deploy/install.sh`:**
  - writes `.env`, `secrets/` and the first config
  - creates the Mosquitto user
  - starts the stack and prints the setup code
  - never overwrites anything on a re-run
- **CI:** builds both images for both architectures and runs the stack end to end.

**Tech Stack:** Docker Engine with Compose v2, Docker Buildx with QEMU (in CI), bash (installer), Python 3.13 stdlib (smoke test), GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-25-cave-phase1-design.md` (sections "Constraints", "Phase 1 scope › Install", "Devices: MQTT", "Scripts", "Exit gate for Phase 1"). Earlier plans: `docs/superpowers/plans/2026-10-*-cave-phase1-plan{1..6}-*.md`.

## Global Constraints

- Runs on Debian 13 "trixie" minimal, amd64 and arm64, installed with Docker Compose.
- `compose.yaml` with profiles `mqtt`, `scripts`; install guide for Debian 13.
- Anything that needs the internet to work is an anti-goal: no vendor cloud, no telemetry, no hosted relay. Building images may download packages; running the stack must not.
- Mosquitto sidecar (Compose profile `mqtt`), with a user and password created by the installer.
- Scripts run only in the `cave-script-runner` container:
  - PowerShell 7, Python 3 and Bash
  - scripts mounted read-only
  - no Docker socket
  - CPU and memory limits
- HTTPS only, self-signed certificate by default; no plain-HTTP listener; no local CA.
- Never log secrets, passwords, tokens or keys (CLAUDE.md). Secrets are files (`*_FILE`), never Compose environment values.
- Never call real devices or the network in unit tests (CLAUDE.md). Docker-dependent checks run in CI, or locally when Docker is running.
- Base images pinned by `@sha256:` digest; no `:latest`.
- Commits: Conventional Commits, `git commit -s`.

## Review Focus

1. **Requests that reach CAVE through Docker's proxy.** With the userland proxy (IPv6, hairpin, some hosts), every request shows the bridge gateway (for example `172.18.0.1`) as its source. "Local network only" must then fail closed, never open: the installer seeds only the host's LAN range, never a Docker network. Pinned in Tasks 1 and 4.
2. **Re-running the installer.** A second run, an upgrade or a reboot must keep the database, config, certificate, runner token, MQTT password and Mosquitto users. Pinned in Task 4 (dry run twice) and Task 5 (restart keeps the owner).
3. **File ownership.** `cave` runs as uid 10001. If `./data` or `./config` belong to someone else, saving a file or starting fails with an obscure error. The installer must chown them, and the smoke test saves an automation through the API. Pinned in Tasks 4 and 5.
4. **Secrets in the wrong place.** A token or password must not show up in `.env`, `docker compose config`, `docker inspect` output or the logs. Pinned in Tasks 3 and 5.
5. **Running offline.** `docker compose up` after a reboot with no internet must not try to pull or build. Pinned in Task 3 (`pull_policy`) and Task 7 (the unplugged run).

---

## File structure

```
compose.yaml                    the stack (profiles mqtt, scripts)
.dockerignore                   keeps node_modules, data, .venv, secrets out of build contexts
deploy/core/Dockerfile          console build stage + cave-core runtime
deploy/script-runner/Dockerfile (modify) arm64 PowerShell, pinned digests
deploy/mosquitto/mosquitto.conf (exists)
deploy/install.sh               Debian installer (idempotent)
deploy/smoke.py                 end-to-end check of a running stack (stdlib only)
core/cave/envconfig.py          settings, secrets and certificate names from the environment
core/cave/__main__.py           (modify) env-driven serve; `health` subcommand
core/cave/api/app.py            (modify) secrets via envconfig
core/tests/test_envconfig.py, test_health_cli.py, test_deploy_files.py, test_install_script.py
.github/workflows/images.yml    multi-arch builds + compose smoke
docs/install/debian.md          the install guide
docs/exit-gate.md               each gate item → its automated tests + the manual run's results
```

---

### Task 1: Container-ready core: environment settings, secret files, health check

**Files:**
- Create: `core/cave/envconfig.py`, `core/tests/test_envconfig.py`, `core/tests/test_health_cli.py`
- Modify: `core/cave/__main__.py`, `core/cave/api/app.py:55,92`

**Interfaces:**
- Produces:
  - `env_secret(name: str, environ: Mapping[str, str] = os.environ) -> str | None`
    - reads the file named by `{name}_FILE` if that is set, stripping one trailing newline; otherwise reads `{name}`
    - an empty value is `None`
    - a `_FILE` that can't be read raises `SystemExit` with a message naming the variable, not the contents
  - `settings_from_env(data: Path, config: Path, environ) -> Settings`
    - `CAVE_LOCAL_RANGES` and `CAVE_TRUSTED_PROXIES` are comma- or space-separated CIDRs, checked with `ipaddress.ip_network(strict=False)`
    - a bad value exits naming the variable and the value
    - unset means `[]`, which keeps today's detection
  - `cert_names(environ) -> tuple[list[str], list[str]]`
    - `CAVE_HOSTNAMES` (default: `socket.gethostname()` and `localhost`) and `CAVE_HOST_IPS` (default: `host_ipv4()` and `127.0.0.1`)
    - duplicates and empties dropped
  - `python -m cave health [--port 8443]`
    - GETs `https://127.0.0.1:{port}/api/v1/health`, skipping certificate checks (loopback only: the certificate is CAVE's own)
    - exits 0 only for status 200 with `{"status": "ok"}`, 1 otherwise, within a 5 s timeout
  - `serve` reads `settings_from_env` and `cert_names`. `app.py` uses `env_secret("CAVE_MQTT_PASSWORD")` and `env_secret("CAVE_RUNNER_TOKEN")`.
  - `serve` takes `CAVE_CERT` and `CAVE_KEY` (paths) as defaults for `--cert` and `--key`. This is how a container uses your own certificate. Setting only one of them exits with the same "go together" error as the flags.
- Consumes: `Settings`, `netconfig.seed` / `host_ipv4` (Plan 2), `create_app` (Plan 1).

- [ ] **Step 1: Write failing tests**
  - `test_env_secret_prefers_file`: with `X_FILE` set to a temporary file holding `"s3cret\n"` and `X` set to `"other"`, it returns `"s3cret"`
  - `test_env_secret_empty_is_none`
  - `test_env_secret_missing_file_exits_without_contents`
  - `test_settings_from_env_ranges`:
    - `"192.168.1.0/24, 10.0.0.0/8"` gives both ranges
    - `"192.168.1.300/24"` exits with `CAVE_LOCAL_RANGES` in the message
  - `test_unset_ranges_keep_detection`: `local_ranges == []`, so `netconfig.seed` still detects
  - `test_own_cert_from_env`: `CAVE_CERT` with no `CAVE_KEY` exits; both set means `serve` uses them and makes no self-signed certificate (call the argument parsing with `tls.ensure_certificate` monkeypatched to fail)
  - `test_cert_names_from_env`:
    - `CAVE_HOSTNAMES="cave.lan cave"` and `CAVE_HOST_IPS="192.168.1.20"` give those names plus `localhost` and `127.0.0.1`
  - `test_health_ok` and `test_health_fails`, with `urllib.request.urlopen` monkeypatched (no network):
    - exit code 0 for `{"status": "ok"}`
    - exit code 1 for a 503, for a connection error, and for an `ok` body with a non-200 status
- [ ] **Step 2:** Run `pytest tests/test_envconfig.py tests/test_health_cli.py -v`. Expected: FAIL (module missing).
- [ ] **Step 3:** Implement `envconfig.py` and the `health` subcommand. Switch `__main__.serve` and `app.py` to them. Keep the dev runner's `CAVE_RUNNER_TOKEN` fallback.
- [ ] **Step 4:** Run the full `pytest`, then `ruff check .` and `mypy --strict cave`. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "feat(core): environment settings, secret files and a health check"`

---

### Task 2: The images

**Files:**
- Create: `deploy/core/Dockerfile`, `.dockerignore`, `core/tests/test_deploy_files.py`
- Modify: `deploy/script-runner/Dockerfile`

**Interfaces:**
- **`deploy/core/Dockerfile`**, built from the repo root.
  - Stage `console`:
    - base `node:24-trixie-slim@sha256:…`
    - copies `console/` and `schemas/` (the recipe tests read the schemas)
    - runs `corepack enable && pnpm install --frozen-lockfile && pnpm build`. The build writes to `../core/cave/web/console`.
  - Stage `runtime`:
    - base `python:3.13-slim-trixie@sha256:…`
    - copies `core/`, then the built console into `core/cave/web/console`
    - runs `pip install --no-cache-dir /src/core`
    - user `cave` (uid and gid 10001), `WORKDIR /data`, `EXPOSE 8443`
    - `HEALTHCHECK --interval=30s --timeout=6s CMD ["python", "-m", "cave", "health"]`
    - `ENTRYPOINT ["python", "-m", "cave", "serve", "--host", "0.0.0.0", "--port", "8443", "--data", "/data", "--config", "/config"]`
- **`deploy/script-runner/Dockerfile`** gains `ARG TARGETARCH`:
  - `amd64` installs PowerShell from Microsoft's apt repository, as today.
  - `arm64` installs the pinned PowerShell `linux-arm64.tar.gz` from the PowerShell GitHub release:
    - `ARG PWSH_VERSION`, `ARG PWSH_SHA256_ARM64`, checked with `sha256sum -c` before unpacking
    - unpacked to `/opt/microsoft/powershell/7`, with `/usr/bin/pwsh` linked to it
  - Look up the current 7.x LTS version and its published SHA-256 when implementing; never guess them.
  - It drops the "not built yet" shortcut comment.
- **`.dockerignore`** excludes:
  - `**/node_modules`, `**/.venv`, `data`, `secrets`, `.env`
  - `core/cave/web/console`, `**/__pycache__`, `.git`, `.superpowers`
- **`test_deploy_files.py`** (static checks, no Docker):
  - every `FROM` in both Dockerfiles has `@sha256:`
  - no `:latest`
  - the core runtime stage sets a non-root `USER`
  - the runner Dockerfile has no `docker.sock` and checks the arm64 tarball with `sha256sum -c`

- [ ] **Step 1:** Write `test_deploy_files.py` with the checks above. Run it. Expected: FAIL (core Dockerfile missing, runner FROM unpinned).
- [ ] **Step 2:** Write `.dockerignore` and `deploy/core/Dockerfile`, and update the runner Dockerfile. Pin each digest with `docker buildx imagetools inspect <image>:<tag>` (or the registry's digest page when Docker isn't running).
- [ ] **Step 3:** Rerun the tests. Expected: PASS.
- [ ] **Step 4: Build locally** if Docker is running. Otherwise this step moves to Task 5's CI job, and you say so in the ledger.
  - Run `docker buildx build -f deploy/core/Dockerfile --platform linux/amd64,linux/arm64 .` and the same for the runner.
  - Run `docker run --rm --entrypoint pwsh cave-script-runner -NoProfile -Command '$PSVersionTable.PSVersion'` on both architectures (arm64 under QEMU).
  - Expected: both images build, and PowerShell prints 7.x.
- [ ] **Step 5: Commit** `git commit -s -m "build: cave-core and script-runner images for amd64 and arm64"`

---

### Task 3: `compose.yaml`

**Files:**
- Create: `compose.yaml`, `core/tests/test_compose.py`
- Modify: `deploy/mosquitto/mosquitto.conf` (comment only: the passwd file is created by the installer, see Task 4)

**Interfaces (the file Tasks 4 and 5 rely on):**
- **`cave`:**
  - `build: {context: ., dockerfile: deploy/core/Dockerfile}`, `image: cave-core:local`, `pull_policy: never`
  - `ports: ["${CAVE_PORT:-8443}:8443"]`
  - volumes `./data:/data`, `./config:/config`
  - `env_file: .env`, holding only non-secret settings:
    - `CAVE_LOCAL_RANGES`, `CAVE_HOSTNAMES`, `CAVE_HOST_IPS`
    - `CAVE_RUNNER_URL`, empty unless the scripts profile is on
  - `environment`: `CAVE_MQTT_PASSWORD_FILE: /run/secrets/mqtt_password`, `CAVE_RUNNER_TOKEN_FILE: /run/secrets/runner_token`
  - `secrets: [mqtt_password, runner_token]`
  - `read_only: true`, `tmpfs: [/tmp]`, `cap_drop: [ALL]`, `security_opt: ["no-new-privileges:true"]`
  - `restart: unless-stopped`
  - `networks: [default, runner]`
- **`mosquitto`** (`profiles: [mqtt]`):
  - `image: eclipse-mosquitto:2@sha256:…`, `pull_policy: missing`
  - `ports: ["1883:1883"]`
  - volumes:
    - `./deploy/mosquitto/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro`
    - `./secrets/mosquitto_passwd:/mosquitto/config/passwd:ro`
    - `./data/mosquitto:/mosquitto/data`
  - `restart: unless-stopped`
- **`script-runner`** (`profiles: [scripts]`):
  - `build: {context: ., dockerfile: deploy/script-runner/Dockerfile}`, `image: cave-script-runner:local`, `pull_policy: never`
  - `read_only: true`, `tmpfs: [/tmp, /work]`
  - `cap_drop: [ALL]`, `cap_add: [SETUID, SETGID, KILL, CHOWN]`
  - `mem_limit: 512m`, `cpus: 1.0`, `pids_limit: 256`
  - volume `./config/scripts:/scripts:ro`
  - `secrets: [runner_token]`
  - `networks: [runner]` only, with no `ports`
- **`networks.runner`:** `internal: true`.
- **`secrets`:** `mqtt_password: {file: ./secrets/mqtt_password}`, `runner_token: {file: ./secrets/runner_token}`.
- **`CAVE_RUNNER_URL`** is `http://script-runner:8099` when the profile is on.

- [ ] **Step 1: Write `test_compose.py`**, which loads `compose.yaml` with PyYAML (no Docker). Tests:
  - `test_runner_is_unreachable_from_outside`: `script-runner` has no `ports`, its only network is `runner`, and `runner` is `internal: true`
  - `test_no_secret_values_in_environment`: no `environment` or `env_file` value anywhere has a key ending in `TOKEN` or `PASSWORD` unless it ends in `_FILE`
  - `test_hardening`:
    - `cave` and `script-runner` are `read_only`, with `cap_drop: [ALL]`
    - the runner's `cap_add` is exactly `{SETUID, SETGID, KILL, CHOWN}`
    - the runner has `mem_limit` and `cpus`
  - `test_no_docker_socket`: no volume anywhere mentions `docker.sock`
  - `test_offline_restart`: built images have `pull_policy: never`, and every `image:` with a registry has `@sha256:`
  - `test_profiles`: `mosquitto` is in `mqtt` and `script-runner` in `scripts`
- [ ] **Step 2:** Run it. Expected: FAIL (no compose file).
- [ ] **Step 3:** Write `compose.yaml`. If Docker is available, also check that `docker compose --profile mqtt --profile scripts config` validates against a scratch `.env` and `secrets/`.
- [ ] **Step 4:** Rerun. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "build: compose stack with mqtt and scripts profiles"`

---

### Task 4: The installer

**Files:**
- Create: `deploy/install.sh` (executable), `core/tests/test_install_script.py`

**Interfaces:**
- **Usage:** `deploy/install.sh [--profiles mqtt,scripts] [--yes] [--dry-run]`, run from the repo root as a user in the `docker` group, or with sudo.
- **Steps, in order. Each step skips anything that already exists**, so a re-run changes nothing:
  1. Check that `docker compose version` works. If not, print the Debian 13 commands from `docs/install/debian.md` and exit 1.
  2. Find the LAN:
     - `ip -4 route get 192.0.2.1` gives the source address and device; `ip -4 -o addr show dev <dev>` gives the prefix
     - write `CAVE_LOCAL_RANGES` as that network (for example `192.168.1.0/24`), `CAVE_HOST_IPS` as the address, and `CAVE_HOSTNAMES` as `$(hostname) $(hostname).local localhost`
     - **refuse any address inside `172.16.0.0/12` that belongs to a `docker*` or `br-*` device**: never seed a Docker network (Review Focus 1)
  3. Create `data/`, `config/`, `config/scripts/` and `secrets/`. Run `chown -R 10001:10001 data config` (Review Focus 3).
  4. Create the secrets with `head -c 32 /dev/urandom | base64 | tr -d '/+=\n'`:
     - `secrets/runner_token` and `secrets/mqtt_password` (mode `0400`, owned by 10001)
     - an empty `secrets/mosquitto_passwd`, and `data/mosquitto/` (both owned by 1883, Mosquitto's uid in its image; the passwd file holds only hashes, mode `0400`)
  5. With the `mqtt` profile:
     - write `config/mqtt.yaml` (`broker: {host: mosquitto, port: 1883, username: cave}`) if missing
     - create the `cave` Mosquitto user with `docker run --rm -v "$PWD/secrets/mosquitto_passwd:/passwd" "$(docker compose config --images mosquitto)" mosquitto_passwd -b /passwd cave "$(cat secrets/mqtt_password)"`
       - use the same pinned image that Compose runs, and skip this when the file already has a `cave:` line
       - fix the file's ownership afterwards
     - print how to add device users: `mosquitto_passwd` with a different user name
  6. Write `.env` (non-secret settings only): `COMPOSE_PROFILES`, `CAVE_LOCAL_RANGES`, `CAVE_HOST_IPS`, `CAVE_HOSTNAMES`, and `CAVE_RUNNER_URL` (set only with `scripts`).
  7. Run `docker compose build`, then `docker compose up -d`. Wait up to 120 s for `cave` to be `healthy`. Print the URL, the certificate fingerprint and the setup code line from `docker compose logs cave`.
- **`--dry-run`** does steps 2, 3, 4 and 6 only and touches no Docker. `CAVE_INSTALL_ROOT` points it at a scratch folder (default: the repo root), so it can be tested.

- [ ] **Step 1: Write `test_install_script.py`.**
  - Skip on Windows. Otherwise run `bash deploy/install.sh --dry-run --yes --profiles mqtt,scripts` with a fake `ip` script first on `PATH`, `CAVE_INSTALL_ROOT=tmp_path`, and `chown` stubbed to a no-op.
  - Tests:
    - `test_env_has_lan_not_docker`:
      - fake `ip` reports `src 192.168.1.20 dev eth0` with prefix 24, so `.env` holds `CAVE_LOCAL_RANGES=192.168.1.0/24`
      - when it reports `dev docker0` with `172.17.0.1/16`, the script exits non-zero and says to set `CAVE_LOCAL_RANGES` by hand
    - `test_no_secrets_in_env`: `.env` has no line with `TOKEN=` or `PASSWORD=`
    - `test_secret_files_private`: both secret files exist, are mode `0400` and are at least 40 characters
    - `test_rerun_changes_nothing`: a second run leaves every file's bytes and mtime the same (Review Focus 2)
    - `test_scripts_profile_sets_runner_url`: `--profiles mqtt` alone leaves `CAVE_RUNNER_URL=`; with `scripts`, it's `http://script-runner:8099`
- [ ] **Step 2:** Run on Linux (CI, or WSL if you have it). Expected: FAIL.
- [ ] **Step 3:** Write `install.sh` with `set -euo pipefail`. It must pass `shellcheck` with no warnings.
- [ ] **Step 4:** Rerun the tests and `shellcheck deploy/install.sh`. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "feat(deploy): idempotent Debian installer"`

---

### Task 5: CI: multi-arch images and an end-to-end Compose run

**Files:**
- Create: `.github/workflows/images.yml`, `deploy/smoke.py`
- Modify: `core/tests/test_mqtt_client.py` (the live test signs in with `CAVE_MQTT_TEST_USER` when it's set), `.github/workflows/core.yml` (adds `shellcheck deploy/install.sh`)

**Interfaces:**
- `images.yml`, on pull requests and pushes to `main`. Job `build` uses `docker/setup-qemu-action` and `docker/setup-buildx-action`. It builds both images for `linux/amd64,linux/arm64` without pushing. Then it runs `pwsh -Version` in the arm64 runner image under QEMU.
- Job `compose-smoke` (amd64, `ubuntu-latest`) runs:
  1. `deploy/install.sh --yes --profiles mqtt,scripts`
  2. `python3 deploy/smoke.py --url https://127.0.0.1:8443`
  3. `CAVE_MQTT_TEST_BROKER=127.0.0.1:1883 CAVE_MQTT_TEST_USER=cave CAVE_MQTT_PASSWORD_FILE=secrets/mqtt_password pytest core/tests/test_mqtt_client.py::test_live_broker_roundtrip` (run as a user that can read the 0400 secret)
  4. `docker compose restart cave` followed by `smoke.py --after-restart`
  5. `docker compose down` (never `-v`)
- `deploy/smoke.py` uses only the stdlib, with an unverified TLS context for this self-signed localhost check. Each check prints one line. Exit 1 on the first failure. Checks:
  - `/api/v1/health` is ok and the response has the `content-security-policy` header
  - `/enroll` serves no inline script (the Plan 6 review's critical bug, now end to end)
  - setup: reads the code with `docker compose logs cave` and creates the owner with `POST /api/v1/setup`
    - it then computes the TOTP code from `provisioning_uri` with a 20-line RFC 6238 function (stdlib `hmac`, `hashlib`, `base64`) and signs in through `/auth/mfa`
  - `PUT /api/v1/automations/smoke` with a valid automation returns 200 and the file appears in `./config/automations` (Review Focus 3)
  - `tcp 127.0.0.1:8099` refuses: the runner isn't reachable from the host
  - an anonymous MQTT CONNECT (hand-built 14-byte packet) to `127.0.0.1:1883` gets return code 5, not authorized
  - neither `docker compose config` nor `docker inspect <cave>` contains the runner token or MQTT password (Review Focus 4)
  - `--after-restart`: the owner can still sign in (Review Focus 2)

- [ ] **Step 1:** Write `smoke.py`. Point it at a stack that isn't running and check that it fails cleanly on the first check, with exit code 1 and a readable line.
- [ ] **Step 2:** Write `images.yml`, and change `core.yml` and `test_mqtt_client.py`.
- [ ] **Step 3:** If Docker is running locally, run the `compose-smoke` steps by hand (in WSL or Git Bash). Otherwise rely on CI. Record which one in the ledger.
- [ ] **Step 4:** Push a branch only when the user asks. Until then, run the workflow logic locally with `act`, or note that CI is unverified. Expected once CI runs: both jobs green.
- [ ] **Step 5: Commit** `git commit -s -m "ci: multi-arch image builds and an end-to-end compose check"`

---

### Task 6: The install guide

**Files:**
- Create: `docs/install/debian.md`
- Modify: `README.md` (status line and link), `docs/install/tablets.md` (point "Run CAVE for testing" at the guide), `deploy/script-runner/Dockerfile` header comment (now built by Compose)

**Content of `debian.md`, in order:**
1. **What you need:** Debian 13, amd64 or arm64, 2 GB RAM, a fixed LAN address (a DHCP reservation is fine).
2. **Install Docker** from Debian's own packages, `apt install docker.io docker-compose` (check the trixie package names when writing), then add yourself to the `docker` group.
3. **Get CAVE and install:** `git clone`, then `deploy/install.sh`. Say what it creates and that a re-run changes nothing.
4. **First sign-in:** the URL, the certificate warning, checking the fingerprint against the installer's output, and the setup code. Link `docs/console.md`.
5. **Devices:** how to point Zigbee2MQTT, Tasmota, Shelly and ESPHome at `<host>:1883`, and how to add a Mosquitto user per device. Link `docs/integrations/mqtt.md`.
6. **Scripts:** the `scripts` profile, where scripts live (`config/scripts`), and that they run only in the sandbox. Link `docs/scripts.md`.
7. **Running without the internet:**
   - nothing at runtime needs it
   - `docker compose up -d` after a reboot needs no downloads
   - only building (`install.sh`, upgrades) does
8. **Upgrade:** `git pull`, `deploy/install.sh` (rebuilds and restarts), what's kept, and that migrations run on start.
9. **Back up:** stop the stack and copy `data/`, `config/`, `secrets/` and `.env`. Restore by copying them back. (No backups UI in Phase 1.)
10. **Your own certificate:** mount the files read-only and set `CAVE_CERT` and `CAVE_KEY` in `.env` (Task 1), or use a reverse proxy listed under trusted proxies. Link the tablet guide.
11. **When the client address is wrong:** if every request shows a `172.x` address, Docker's proxy is in the way and "Local network only" items are refused. Say how to check this in the sign-in log, and how to fix it (`"userland-proxy": false` in `/etc/docker/daemon.json`, or IPv4 access). Review Focus 1.
12. **Uninstall:** `docker compose down`, then delete the folder.

- [ ] **Step 1:** Write the guide. Every command in it must be one that Task 4 or 5 ran, or one quoted from Debian or Docker documentation fetched when writing.
- [ ] **Step 2:** Update the README status: "Phase 1 installs on Debian 13 with Docker Compose; see the install guide." Update the other links.
- [ ] **Step 3: Commit** `git commit -s -m "docs: Debian 13 install guide"`

---

### Task 7: The Phase 1 exit gate

**Files:**
- Create: `docs/exit-gate.md`
- Modify: whatever the run turns up, each fix test-first in the task that owns the code

**Interfaces:** `docs/exit-gate.md` has one section per gate item (spec "Exit gate for Phase 1", items 1 to 4). Each section lists:
- the automated tests that cover it, by `file::test`. Existing ones:
  - item 1: `test_mqtt_discovery.py::test_z2m_light_json_schema`, `test_mqtt_bridge.py::test_toggle_uses_current_state`, and the live-broker test from Task 5
  - item 2: `test_guards.py::test_kids_dashboard_cannot_open_garage`, `test_guards.py::test_garage_tablet_only_on_lan`, `test_guards.py::test_command_from_wan_refused_on_local_item`, `test_screen_auth.py::test_unenrolled_or_other_screen_refused`, `test_tokens.py::test_other_users_token_cannot_command`, plus the household-browser refusal test (find it, or add `test_exit_gate.py::test_household_browser_refused_garage` if none exists)
  - item 3: `test_whatif.py::test_ups_example_whole_run`, `test_whatif.py::test_ups_example_step_two_only`
  - item 4: `test_script_exit_gate.py::test_powershell_script_from_a_dashboard_button`
- the manual check on the real box, with its result and date.

- [ ] **Step 1:** Write `docs/exit-gate.md` with the test map. Run every listed test by name. Expected: PASS. Add any test that's missing.
- [ ] **Step 2: Ask the user** for the Debian 13 box: a spare machine, a VM, or SSH access to one, amd64 or arm64. Don't go on without it. Install with `deploy/install.sh --profiles mqtt,scripts` while online. Pair one Zigbee lamp through Zigbee2MQTT (the user brings the coordinator), and enroll one tablet.
- [ ] **Step 3: Unplug the internet** (pull the uplink cable, or block it at the router; the LAN stays up). Reboot the box. Run `docker compose ps` and check it's all healthy with no pulls. Then walk the four gate items by hand, and record each result in `docs/exit-gate.md`:
  1. the lamp appears and toggles from an Actions dashboard
  2. the five Garage refusals: a household browser, a second unenrolled tablet, the tablet on a phone hotspot (outside the range), another user's token with `curl`, and a command through Kids
  3. the UPS automation in the Test Center, whole and from step 2, with a summary of 0, 0, 0
  4. the PowerShell script from a dashboard button, then its audit log entry
- [ ] **Step 4:** For anything that fails, add a failing test in the owning module, fix it, and re-run that gate item. Record the fix.
- [ ] **Step 5:** Run the full Python suite and console checks. Expected: PASS.
- [ ] **Step 6: Commit** `git commit -s -m "docs: Phase 1 exit gate results"`

---

## Plan 7 done when

- `compose.yaml`, both images and `install.sh` exist. CI builds amd64 and arm64 and the end-to-end Compose check passes.
- A re-run of the installer changes nothing. No secret appears in `.env`, Compose config, `docker inspect` output or logs.
- `docs/install/debian.md` takes a person from a fresh Debian 13 box to signed in.
- All four exit-gate items pass on a real Debian 13 box with the internet unplugged, and `docs/exit-gate.md` records it.
- Still open before going public (spec): the name and trademark check, and the GitHub org. Pushing and publishing images wait for those.
