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
