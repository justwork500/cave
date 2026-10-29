from typing import Literal

import pytest
from pydantic import BaseModel, ConfigDict

from cave.config.yamlfile import ConfigError, load_file, load_text, validate


class _S(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Step(_S):
    type: Literal["call"]
    target: str


class Doc(_S):
    name: str
    actions: list[Step]


TEXT = """\
name: test
actions:
  - type: call
    target: light.a
  - type: call
    target: light.b
  - type: call
    colour: red
"""


def test_line_of_unknown_key():
    with pytest.raises(ConfigError) as e:
        validate(Doc, load_text(TEXT, "t.yaml"), "t.yaml")
    assert str(e.value) == "t.yaml:8: actions[2].colour: Extra inputs are not permitted"
    assert e.value.line == 8 and e.value.path == "actions[2].colour"


def test_line_of_nested_list_item():
    doc = load_text(TEXT, "t.yaml")
    assert doc.lines[("actions", 1, "target")] == 6
    assert doc.lines[("actions", 2)] == 7


def test_missing_key_points_at_parent_line():
    text = "name: x\nactions:\n  - type: call\n"
    with pytest.raises(ConfigError) as e:
        validate(Doc, load_text(text, "t.yaml"), "t.yaml")
    assert e.value.path == "actions[0].target" and e.value.line == 3


def test_yaml_syntax_error_has_line():
    with pytest.raises(ConfigError) as e:
        load_text("name: x\nactions: [unclosed\n", "t.yaml")
    assert e.value.line is not None and str(e.value).startswith("t.yaml:")


def test_aliases_refused():
    with pytest.raises(ConfigError, match="anchors and aliases"):
        load_text("a: &x 1\nb: *x\n", "t.yaml")


def test_oversize_refused(tmp_path):
    p = tmp_path / "big.yaml"
    p.write_text("a: " + "x" * (256 * 1024) + "\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="too large"):
        load_file(p)


def test_empty_document_is_none():
    assert load_text("", "t.yaml").data is None
