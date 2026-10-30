"""Spec exit-gate item 4, as far as it goes without Docker:
a PowerShell script runs from a dashboard button in the sandbox, and its result shows in the audit log."""

import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cave import audit
from cave.access.items import set_assignments
from cave.state import Entity
from tests.conftest import sign_in
from tests.test_script_service import runner_for

FIX = Path(__file__).parent / "fixtures" / "config"

DASHBOARD = """\
dashboard:
  title: Lab
  views:
    - id: main
      title: Lab
      sections:
        - title: Power
          cards:
            - type: button
              name: Shut down lab
              action: sequence.lab_safe_shutdown
              confirm: true
"""


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="PowerShell 7 isn't installed")
def test_powershell_script_from_a_dashboard_button(app, users):
    config = app.state.settings.config_dir
    for folder, name in (("sequences", "lab_safe_shutdown.yaml"), ("scripts", "Stop-LabHosts.ps1")):
        (config / folder).mkdir(exist_ok=True)
        (config / folder / name).write_text((FIX / folder / name).read_text(encoding="utf-8"), encoding="utf-8")
    (config / "dashboards").mkdir(exist_ok=True)
    (config / "dashboards" / "lab.yaml").write_text(DASHBOARD, encoding="utf-8")
    app.state.config.load_all()
    app.state.scripts.load_all()
    app.state.script_service.runner = runner_for(config / "scripts")
    app.state.states.register(Entity("switch.proxmox_vm_media", "Media VM", None, "switch"))
    switched = []

    async def handler(entity_id, command, args):
        switched.append((entity_id, command))

    app.state.states.set_command_handler("switch", handler)
    # sam gets the dashboard and the routine behind its button, nothing else
    set_assignments(app.state.db, "test", "dashboard:lab", [("user", users.sam.id)])
    set_assignments(app.state.db, "test", "sequence:lab_safe_shutdown", [("user", users.sam.id)])

    with TestClient(app, base_url="https://testserver", client=("192.168.1.5", 50000)) as c:
        sign_in(c, "sam", "pw-sam-1234")
        r = c.post("/api/v1/sequences/lab_safe_shutdown/run", json={})
        assert r.status_code == 200, r.text
        for _ in range(300):
            entry = next((e for e in audit.list_entries(app.state.db) if e["action"] == "script.run"), None)
            if entry:
                break
            time.sleep(0.05)
    assert entry is not None, "the script never ran"
    assert entry["target"] == "script:Stop-LabHosts.ps1"
    assert entry["new"]["outcome"] == "finished"
    assert entry["new"]["result"] == {"status": "3 hosts stopped", "stopped": 3}
    assert switched == [("switch.proxmox_vm_media", "turn_off")]
