from datetime import time, timedelta
from pathlib import Path

import pytest

from cave.config.models import AutomationFile, DashboardFile, SequenceFile, check_nesting
from cave.config.refs import refs
from cave.config.yamlfile import ConfigError, load_file, load_text, validate

FIX = Path(__file__).parent / "fixtures" / "config"


def automation(text: str):
    return validate(AutomationFile, load_text(text, "a.yaml"), "a.yaml").automation


def ups():
    return validate(AutomationFile, load_file(FIX / "automations" / "ups-on-battery.yaml"), "ups-on-battery.yaml")


def test_framework_ups_example_validates():
    a = ups().automation
    assert a.id == "ups-on-battery" and a.mode == "single" and a.max == 10
    assert a.triggers[0].for_ == timedelta(minutes=2)
    assert [x.type for x in a.actions] == ["notify", "sequence", "wait_for", "notify"]
    assert a.actions[2].timeout == timedelta(hours=1)
    s = validate(SequenceFile, load_file(FIX / "sequences" / "lab_safe_shutdown.yaml"), "l.yaml").sequence
    assert s.fields["grace_seconds"].default == 60 and s.actions[1].result_var == "lab"


BASE = """\
automation:
  id: a
  name: A
  triggers:
    - type: startup
  actions:
"""


def test_unknown_action_type_error_names_line():
    with pytest.raises(ConfigError) as e:
        automation(BASE + "    - type: call\n      target: light.a\n      command: turn_on\n    - type: teleport\n")
    assert e.value.line == 10 and "actions[1]" in e.value.path


def test_repeat_needs_exactly_one_mode():
    body = "    - type: repeat\n      count: 2\n      until:\n        - type: state\n          entity: a.b\n" \
           "          state: 'on'\n      actions:\n        - type: stop\n"
    with pytest.raises(ConfigError, match="exactly one"):
        automation(BASE + body)
    with pytest.raises(ConfigError, match="exactly one"):
        automation(BASE + "    - type: repeat\n      actions:\n        - type: stop\n")


@pytest.mark.parametrize(("raw", "expected"), [
    ('"00:02:00"', timedelta(minutes=2)), ('"2:00"', timedelta(minutes=2)), ("120", timedelta(minutes=2)),
    ("00:02:00", timedelta(minutes=2)),  # unquoted: YAML 1.1 reads this as the number 120
])
def test_durations(raw, expected):
    a = automation(BASE + f"    - type: delay\n      duration: {raw}\n")
    assert a.actions[0].duration == expected


def test_duration_over_a_day_refused():
    with pytest.raises(ConfigError, match="24 hours"):
        automation(BASE + '    - type: delay\n      duration: "25:00:00"\n')


def test_time_trigger_quoted_and_unquoted():
    t = automation(BASE.replace("type: startup", 'type: time\n      at: "07:30"') + "    - type: stop\n")
    assert t.triggers[0].at == time(7, 30)
    u = automation(BASE.replace("type: startup", "type: time\n      at: 07:30") + "    - type: stop\n")
    assert u.triggers[0].at == time(7, 30)


def test_nesting_cap():
    body = "    - type: choose\n      options:\n        - conditions: []\n          actions:\n"
    deep = ""
    indent = "            "
    for _ in range(9):
        deep += f"{indent}- type: choose\n{indent}  options:\n{indent}    - conditions: []\n{indent}      actions:\n"
        indent += "        "
    deep += f"{indent}- type: stop\n"
    doc = load_text(BASE + body + deep, "a.yaml")
    a = validate(AutomationFile, doc, "a.yaml").automation
    with pytest.raises(ConfigError, match="nest"):
        check_nesting(a, doc, "a.yaml")


def test_dashboard_cards():
    d = validate(DashboardFile, load_file(FIX / "dashboards" / "home.yaml"), "home.yaml").dashboard
    cards = [c for s in d.views[0].sections for c in s.cards]
    assert [c.type for c in cards] == ["tile", "gauge", "button", "markdown"]
    assert cards[0].w == 3 and cards[2].action == "sequence.lab_safe_shutdown"


def test_visible_to_is_unknown_key():
    with pytest.raises(ConfigError, match="visible_to"):
        validate(DashboardFile, load_text("dashboard:\n  title: x\n  visible_to: [admin]\n  views: []\n", "d.yaml"),
                 "d.yaml")


def test_button_needs_action_or_entity_command():
    text = "dashboard:\n  title: x\n  views:\n    - id: v\n      title: V\n      sections:\n" \
           "        - title: S\n          cards:\n            - type: button\n              name: B\n"
    with pytest.raises(ConfigError, match="action"):
        validate(DashboardFile, load_text(text, "d.yaml"), "d.yaml")


def test_refs_collects_everything():
    r = refs(ups().automation)
    assert r.entities == {"binary_sensor.ups_on_battery", "sensor.ups_battery_runtime_min"}
    assert r.sequences == {"lab_safe_shutdown"} and not r.dynamic_template
    s = validate(SequenceFile, load_file(FIX / "sequences" / "lab_safe_shutdown.yaml"), "l.yaml").sequence
    rs = refs(s)
    assert rs.entities == {"switch.proxmox_vm_media"} and rs.scripts == {"scripts/Stop-LabHosts.ps1"}


def test_refs_dashboard_and_markdown_template():
    d = validate(DashboardFile, load_file(FIX / "dashboards" / "home.yaml"), "home.yaml").dashboard
    r = refs(d)
    assert r.entities == {"light.living_room", "sensor.ups_load_pct", "sensor.ups_battery_runtime_min"}
    assert r.sequences == {"lab_safe_shutdown"}


def test_refs_dynamic_template():
    a = automation(BASE + "    - type: notify\n      message: \"{{ states(x) }}\"\n")
    assert refs(a).dynamic_template
