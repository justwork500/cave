import time

import pytest

from cave.templates import TemplateError, render_value


def test_value_json_path():
    assert render_value("{{ value_json.state }}", '{"state": "ON"}') == "ON"


def test_value_plain():
    assert render_value("{{ value }}", "21.5") == "21.5"


def test_filters_float_round():
    assert render_value("{{ value_json.t | float | round(1) }}", '{"t": "21.456"}') == "21.5"


def test_tasmota_brackets():
    assert render_value("{{ value_json['ENERGY']['Power'] }}", '{"ENERGY": {"Power": 12}}') == "12"


def test_boolean_renders_as_python_word():
    assert render_value("{{ value_json.contact }}", '{"contact": false}') == "False"


def test_sandbox_blocks_dunder():  # Review Focus 3
    with pytest.raises(TemplateError):
        render_value("{{ ''.__class__.__mro__ }}", "{}")
    with pytest.raises(TemplateError):
        render_value("{{ value_json.__class__.__init__.__globals__ }}", "{}")


def test_huge_range_refused():  # Review Focus 3
    start = time.monotonic()
    with pytest.raises(TemplateError):
        render_value("{{ range(10**9) | list }}", "{}")
    assert time.monotonic() - start < 2


def test_syntax_error_is_template_error():
    with pytest.raises(TemplateError):
        render_value("{{ value_json.state ", "{}")


def test_value_json_undefined_for_non_json():
    with pytest.raises(TemplateError):
        render_value("{{ value_json.state }}", "not json")
    assert render_value("{{ value }}", "not json") == "not json"


def test_missing_key_is_template_error():
    with pytest.raises(TemplateError):
        render_value("{{ value_json.missing }}", '{"state": "ON"}')


def test_string_repeat_bomb_refused():  # Review Focus 3
    with pytest.raises(TemplateError):
        render_value("{{ 'x' * 1000000000 }}", "{}")
    with pytest.raises(TemplateError):
        render_value("{{ 9 ** 9999999 }}", "{}")
    assert render_value("{{ 'ab' * 2 }}", "{}") == "abab"


# ---- automation templates (Plan 4) ----
from datetime import UTC, datetime

from cave.state import Entity, EventBus, StateMachine
from cave.templates import entity_refs, render

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def reader():
    sm = StateMachine(EventBus())
    sm.register(Entity("sensor.ups_runtime", "UPS runtime", None, "sensor"))
    sm.register(Entity("lock.front", "Front", None, "lock"))
    sm.set("sensor.ups_runtime", "12", {"unit_of_measurement": "min"})
    sm.set("lock.front", "locked")
    return sm


def test_states_reads_reader():
    assert render("{{ states('sensor.ups_runtime') }} min left", {}, reader(), NOW) == "12 min left"


def test_is_state_and_state_attr():
    r = reader()
    assert render("{{ is_state('lock.front', 'locked') }}", {}, r, NOW) == "True"
    assert render("{{ state_attr('sensor.ups_runtime', 'unit_of_measurement') }}", {}, r, NOW) == "min"


def test_variables_and_now():
    assert render("{{ lab.status }} at {{ now().hour }}", {"lab": {"status": "ok"}}, reader(), NOW) == "ok at 12"


def test_unknown_entity_is_unknown():
    assert render("{{ states('sensor.nope') }}", {}, reader(), NOW) == "unknown"


def test_render_value_still_refuses_calls():
    with pytest.raises(TemplateError):
        render_value("{{ states('sensor.a') }}", "{}")


@pytest.mark.parametrize("t", ["{{ range(3) | list }}", "{{ lipsum() }}", "{{ value.upper() }}", "{{ dict(a=1) }}"])
def test_other_calls_refused(t):
    with pytest.raises(TemplateError):
        render(t, {"value": "x"}, reader(), NOW)


def test_entity_refs_literal():
    refs, dynamic = entity_refs("{{ states('sensor.a') }} {{ is_state('lock.b', 'locked') }} {{ state_attr('c.d', 'x') }}")
    assert refs == {"sensor.a", "lock.b", "c.d"} and not dynamic


@pytest.mark.parametrize("t", ["{{ states(x) }}", "{{ states('cover.' ~ n) }}", "{% set e = 'a.b' %}{{ states(e) }}"])
def test_entity_refs_dynamic(t):  # Review Focus 2
    assert entity_refs(t)[1]


def test_entity_refs_plain_text():
    assert entity_refs("no templates here") == (frozenset(), False)
