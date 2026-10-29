from datetime import datetime

import pytest

from cave.automation.engine import Engine
from tests.engine_helpers import NOON, DictReader, FakeEffects, automation, run, sequence

LAB = sequence("""\
sequence:
  id: lab
  name: Lab
  fields:
    grace_seconds: { type: int, default: 60 }
  actions:
    - type: set_variable
      name: inner
      value: "x"
    - type: call
      target: switch.vm
      command: turn_off
      args:
        grace: "{{ grace_seconds }}"
""")

LOOP = sequence("""\
sequence:
  id: loop
  name: Loop
  actions:
    - type: sequence
      ref: sequence.loop
""")


def engine(reader=None, effects=None, now=NOON):
    reader = reader or DictReader()
    effects = effects or FakeEffects(reader)
    seqs = {"lab": LAB, "loop": LOOP}
    return Engine(reader, effects, seqs.get, lambda: now), effects


def test_actions_run_in_order_with_trace():
    a = automation("""\
    - type: call
      target: light.a
      command: turn_on
    - type: delay
      duration: 5
    - type: mqtt_publish
      topic: x/y
      payload: hi
""")
    e, fx = engine()
    t = run(e.run(a.actions, {}, source="test"))
    assert t.outcome == "finished"
    assert [s.path for s in t.steps] == ["actions[0]", "actions[1]", "actions[2]"]
    assert fx.calls == [("call", "light.a", "turn_on", {}), ("sleep", 5.0), ("mqtt", "x/y", "hi", False)]


def test_templates_render_with_variables_and_states():
    a = automation("""\
    - type: notify
      title: "Hi {{ who }}"
      message: "{{ states('sensor.t') }} degrees"
""")
    e, fx = engine(DictReader({"sensor.t": "21"}))
    run(e.run(a.actions, {"who": "Sam"}, source="test"))
    assert fx.calls == [("notify", (), "Hi Sam", "21 degrees")]


def test_choose_and_default():
    a = automation("""\
    - type: choose
      options:
        - conditions:
            - type: state
              entity: lock.a
              state: unlocked
          actions:
            - type: call
              target: lock.a
              command: lock
      default:
        - type: stop
          reason: already locked
""")
    e, fx = engine(DictReader({"lock.a": "unlocked"}))
    assert run(e.run(a.actions, {}, source="t")).outcome == "finished" and fx.calls[0][2] == "lock"
    e, fx = engine(DictReader({"lock.a": "locked"}))
    t = run(e.run(a.actions, {}, source="t"))
    assert t.outcome == "stopped" and fx.calls == []


def test_repeat_count_while_until_and_cap():
    count = automation("    - type: repeat\n      count: 3\n      actions:\n        - type: delay\n          duration: 1\n")
    e, fx = engine()
    run(e.run(count.actions, {}, source="t"))
    assert len(fx.calls) == 3
    until = automation("""\
    - type: repeat
      until:
        - type: state
          entity: light.a
          state: "on"
      actions:
        - type: call
          target: light.a
          command: turn_on
""")
    e, fx = engine(DictReader({"light.a": "off"}))
    run(e.run(until.actions, {}, source="t"))
    assert len(fx.calls) == 1
    forever = automation("""\
    - type: repeat
      while:
        - type: template
          value: "true"
      actions:
        - type: delay
          duration: 0
""")
    e, fx = engine()
    t = run(e.run(forever.actions, {}, source="t"))
    assert len(fx.calls) == 1000 and t.outcome == "finished"


def test_wait_for_timeout_stop_and_continue():
    stop = automation("""\
    - type: wait_for
      entity: binary_sensor.ups
      to: "off"
      timeout: 60
    - type: delay
      duration: 1
""")
    e, fx = engine(effects=FakeEffects(wait_result=False))
    t = run(e.run(stop.actions, {}, source="t"))
    assert t.outcome == "stopped" and len(fx.calls) == 1
    cont = automation("""\
    - type: wait_for
      entity: binary_sensor.ups
      to: "off"
      timeout: 60
      on_timeout: continue
    - type: delay
      duration: 1
""")
    e, fx = engine(effects=FakeEffects(wait_result=False))
    assert run(e.run(cont.actions, {}, source="t")).outcome == "finished" and len(fx.calls) == 2


def test_sequence_fields_defaults_and_scope():
    a = automation("""\
    - type: sequence
      ref: sequence.lab
      with:
        grace_seconds: "{{ 60 * 2 }}"
    - type: notify
      message: "{{ inner is defined }}"
""")
    e, fx = engine()
    t = run(e.run(a.actions, {}, source="t"))
    assert t.outcome == "finished"
    assert fx.calls[0] == ("call", "switch.vm", "turn_off", {"grace": "120"})
    assert fx.calls[1] == ("notify", (), None, "False")  # the routine's variables don't leak out


def test_sequence_bad_field_and_missing_routine():
    bad = automation("    - type: sequence\n      ref: sequence.lab\n      with:\n        grace_seconds: soon\n")
    e, _ = engine()
    assert run(e.run(bad.actions, {}, source="t")).outcome == "failed"
    missing = automation("    - type: sequence\n      ref: sequence.nope\n")
    t = run(e.run(missing.actions, {}, source="t"))
    assert t.outcome == "failed" and "nope" in t.error


def test_sequence_recursion_capped():
    a = automation("    - type: sequence\n      ref: sequence.loop\n")
    e, _ = engine()
    t = run(e.run(a.actions, {}, source="t"))
    assert t.outcome == "failed" and "deep" in t.error


def test_script_result_var():
    a = automation("""\
    - type: script
      ref: scripts/x.ps1
      args:
        n: "{{ 1 + 1 }}"
      result_var: lab
    - type: notify
      message: "{{ lab.status }}"
""")
    e, fx = engine()
    run(e.run(a.actions, {}, source="t"))
    assert fx.calls == [("script", "scripts/x.ps1", None, {"n": "2"}), ("notify", (), None, "ok")]


def test_stop_and_failure_outcomes():
    e, _ = engine()
    t = run(e.run(automation("    - type: stop\n      reason: done\n").actions, {}, source="t"))
    assert t.outcome == "stopped"
    t = run(e.run(automation('    - type: notify\n      message: "{{ missing.x }}"\n').actions, {}, source="t"))
    assert t.outcome == "failed" and t.steps[-1].result == "failed" and t.error


def test_start_at_skips_earlier_steps_nested():
    a = automation("""\
    - type: call
      target: light.a
      command: turn_on
    - type: choose
      options:
        - conditions:
            - type: state
              entity: lock.a
              state: never
          actions:
            - type: call
              target: light.b
              command: turn_on
            - type: call
              target: light.c
              command: turn_on
    - type: call
      target: light.d
      command: turn_on
""")
    e, fx = engine()
    t = run(e.run(a.actions, {}, start_at="actions[1].options[0].actions[1]", source="t"))
    assert [c[1] for c in fx.calls] == ["light.c", "light.d"]
    assert [s.result for s in t.steps][:1] == ["skipped"]
    e, fx = engine()
    run(e.run(a.actions, {}, start_at="actions[2]", source="t"))
    assert [c[1] for c in fx.calls] == ["light.d"]


def test_start_at_unknown_path_fails():
    e, _ = engine()
    t = run(e.run(automation("    - type: stop\n").actions, {}, start_at="actions[9]", source="t"))
    assert t.outcome == "failed" and "actions[9]" in t.error


@pytest.mark.parametrize(("cond", "values", "now", "expected"), [
    ("type: state\n      entity: a.b\n      state: [x, y]", {"a.b": "y"}, NOON, True),
    ("type: numeric_state\n      entity: a.b\n      below: 15", {"a.b": "12"}, NOON, True),
    ("type: numeric_state\n      entity: a.b\n      below: 15", {"a.b": "unavailable"}, NOON, False),
    ("type: numeric_state\n      entity: a.b\n      above: 10\n      below: 15", {"a.b": "15"}, NOON, False),
    ('type: time\n      after: "22:00"\n      before: "06:00"', {}, datetime(2026, 1, 7, 23, 30), True),
    ('type: time\n      after: "22:00"\n      before: "06:00"', {}, datetime(2026, 1, 7, 5, 59), True),
    ('type: time\n      after: "22:00"\n      before: "06:00"', {}, NOON, False),
    ("type: time\n      weekdays: [sat, sun]", {}, NOON, False),
    ("type: time\n      weekdays: [wed]", {}, NOON, True),
    ('type: template\n      value: "{{ 1 > 0 }}"', {}, NOON, True),
    ("type: not\n      conditions:\n        - type: state\n          entity: a.b\n          state: x",
     {"a.b": "x"}, NOON, False),
    (("type: or\n      conditions:\n        - type: state\n          entity: a.b\n          state: x\n"
      "        - type: state\n          entity: a.b\n          state: y"), {"a.b": "y"}, NOON, True),
])
def test_conditions_all_types(cond, values, now, expected):
    a = automation("    - type: stop\n", extra=f"  conditions:\n    - {cond}\n")
    e, _ = engine(DictReader(values), now=now)
    ok, steps = run(e.check(a.conditions, {}))
    assert ok is expected and steps
