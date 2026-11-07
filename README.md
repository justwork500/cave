# CAVE

CAVE is a local-first smart-home hub that runs on hardware you own and works without a vendor cloud.

It doesn't try to beat Home Assistant on device count. It aims to beat it on **running a house well**:

- **Access control like Entra and Intune.** Every dashboard, action and console section has one simple pattern: enabled or disabled; show, hide or restrict; and restrict assigns it to users, groups, roles or specific screens (such as a wall tablet). The server enforces it on every request.
- **An admin console that behaves like an enterprise admin center**, with an audit log of every change.
- **PowerShell, Python and Bash scripts** as first-class automation steps.
- **A Test Center** that works like `-WhatIf`: simulate inputs to a real automation and see what it would do, without touching anything.
- **Plain-language dashboards** of standard actions. Household members never see an entity ID.

CAVE runs on Debian 13 with Docker Compose. Nothing in it needs the internet.

## Status

Phase 1 installs on Debian 13 with Docker Compose: see the [install guide](docs/install/debian.md). See also the [Phase 1 design](docs/superpowers/specs/2026-10-25-cave-phase1-design.md) and the longer-term [design framework](docs/CAVE-Design-Framework.md).

## Develop

```bash
python -m venv .venv
.venv/bin/pip install -e "core[dev]"
cd core && ../.venv/bin/pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md). Wall tablets: [docs/install/tablets.md](docs/install/tablets.md). MQTT devices: [docs/integrations/mqtt.md](docs/integrations/mqtt.md). Kasa plugs: [docs/integrations/kasa.md](docs/integrations/kasa.md). Automations: [docs/automations.md](docs/automations.md). Scripts: [docs/scripts.md](docs/scripts.md). The console: [docs/console.md](docs/console.md). Dashboards: [docs/dashboards.md](docs/dashboards.md).

## License

Apache-2.0. See [LICENSE](LICENSE).
