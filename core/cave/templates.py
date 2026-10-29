"""Sandboxed Jinja for value templates. Templates come from devices and other untrusted sources.

A value template only needs to pick a value out of a payload and maybe convert or compare it. So templates are
checked against an allow-list when first compiled: no loops, no macros, no method or function calls, and only a
few filters. With that, rendering time and memory are bounded by the template and payload sizes, and the
operators that could still blow up memory (`*`, `**`, `%`) are capped on top.
"""

import json
import operator
import re
from collections.abc import Mapping
from datetime import datetime
from functools import lru_cache
from typing import Any, Protocol

from jinja2 import StrictUndefined, Template, nodes
from jinja2 import TemplateError as JinjaError
from jinja2.sandbox import ImmutableSandboxedEnvironment

from cave.state import State

MAX_RESULT = 64 * 1024  # longest string or list one operation may build
MAX_INT_BITS = 4096  # largest number `**` may produce
ALLOWED_FILTERS = frozenset({
    "abs", "d", "default", "first", "float", "int", "last", "length", "lower", "replace", "round", "string",
    "tojson", "trim", "upper",
})
ALLOWED_NODES: tuple[type[nodes.Node], ...] = (
    nodes.Template, nodes.Output, nodes.TemplateData, nodes.If, nodes.Assign,
    nodes.Name, nodes.Const, nodes.List, nodes.Tuple, nodes.Dict, nodes.Pair, nodes.Keyword,
    nodes.Getattr, nodes.Getitem, nodes.Slice, nodes.Filter, nodes.Test, nodes.CondExpr,
    nodes.Compare, nodes.Operand, nodes.And, nodes.Or, nodes.Not, nodes.Neg, nodes.Pos,
    nodes.Add, nodes.Sub, nodes.Mul, nodes.Div, nodes.FloorDiv, nodes.Mod, nodes.Pow, nodes.Concat,
)
_WIDE_FORMAT = re.compile(r"\d{4,}")  # a %-format width or precision of 1000+ characters


class TemplateError(Exception):
    pass


def _too_big(value: Any) -> bool:
    return isinstance(value, str | list | tuple) and len(value) > MAX_RESULT


def _safe_replace(value: Any, old_value: Any, new_value: Any, count: int | None = None) -> str:
    s, old, new = str(value), str(old_value), str(new_value)
    hits = s.count(old) if old else len(s) + 1
    if count is not None:
        hits = min(hits, count)
    if len(s) + hits * max(0, len(new) - len(old)) > MAX_RESULT:
        raise TemplateError("result too large")
    return s.replace(old, new) if count is None else s.replace(old, new, count)


class _Env(ImmutableSandboxedEnvironment):
    intercepted_binops = frozenset({"*", "**", "%"})

    def call_binop(self, context: Any, operator_name: str, left: Any, right: Any) -> Any:
        if operator_name == "**":
            if isinstance(left, int) and isinstance(right, int) and right > 0:
                if left.bit_length() * right > MAX_INT_BITS:
                    raise TemplateError("number too large")
            elif isinstance(right, int | float) and abs(right) > 64:
                raise TemplateError("exponent too large")
            return operator.pow(left, right)
        if operator_name == "%":
            if isinstance(left, str) and _WIDE_FORMAT.search(left):
                raise TemplateError("format width too large")
            return operator.mod(left, right)
        for seq, n in ((left, right), (right, left)):
            if isinstance(seq, str | list | tuple) and isinstance(n, int) and len(seq) * n > MAX_RESULT:
                raise TemplateError("result too large")
        return operator.mul(left, right)


_ENV = _Env(autoescape=False, undefined=StrictUndefined)
_ENV.filters = {name: f for name, f in _ENV.filters.items() if name in ALLOWED_FILTERS}
_ENV.filters["replace"] = _safe_replace
_ENV.globals.clear()  # no range(), lipsum(), dict(), cycler() …


STATE_CALLS = frozenset({"states", "is_state", "state_attr", "now"})
_ENTITY_CALLS = frozenset({"states", "is_state", "state_attr"})


def _parse(source: str) -> nodes.Template:
    try:
        return _ENV.parse(source)
    except JinjaError as e:
        raise TemplateError(str(e)) from e


def check(source: str, allowed_calls: frozenset[str] = frozenset()) -> None:
    """Raise TemplateError if the template uses anything outside the allow-list."""
    for node in _parse(source).find_all(nodes.Node):
        if isinstance(node, nodes.Call):
            if not (isinstance(node.node, nodes.Name) and node.node.name in allowed_calls):
                raise TemplateError("templates can't call functions or methods here")
            continue
        if not isinstance(node, ALLOWED_NODES):
            raise TemplateError(f"templates can't use {type(node).__name__.lower()} here")
        if isinstance(node, nodes.Filter) and node.name not in ALLOWED_FILTERS:
            raise TemplateError(f"templates can't use the {node.name!r} filter")


@lru_cache(maxsize=512)
def _compile(source: str, allowed_calls: frozenset[str] = frozenset()) -> Template:
    check(source, allowed_calls)
    return _ENV.from_string(source)


def _render(template: Template, variables: Mapping[str, Any]) -> str:
    try:
        out = str(template.render(variables))
    except TemplateError:
        raise
    except (JinjaError, ArithmeticError, TypeError, ValueError, RecursionError, MemoryError) as e:
        raise TemplateError(str(e)) from e
    if _too_big(out):
        raise TemplateError("result too large")
    return out


class StateReader(Protocol):
    def get(self, entity_id: str) -> State | None: ...


def render(template: str, variables: Mapping[str, Any], reader: StateReader, now: datetime) -> str:
    """Automation templates: the same allow-list, plus states(), is_state(), state_attr() and now()."""

    def states(entity_id: str) -> str:
        s = reader.get(entity_id)
        return s.value if s else "unknown"

    def state_attr(entity_id: str, name: str) -> Any:
        s = reader.get(entity_id)
        return s.attributes.get(name) if s else None

    calls = {
        "states": states,
        "is_state": lambda entity_id, value: states(entity_id) == value,
        "state_attr": state_attr,
        "now": lambda: now,
    }
    return _render(_compile(template, STATE_CALLS), {**variables, **calls})


def entity_refs(template: str) -> tuple[frozenset[str], bool]:
    """Entity ids a template reads, and whether any read uses something other than a string literal."""
    if "{" not in template:
        return frozenset(), False
    found: set[str] = set()
    dynamic = False
    for call in _parse(template).find_all(nodes.Call):
        if isinstance(call.node, nodes.Name) and call.node.name in _ENTITY_CALLS:
            first = call.args[0] if call.args else None
            if isinstance(first, nodes.Const) and isinstance(first.value, str):
                found.add(first.value)
            else:
                dynamic = True
    return frozenset(found), dynamic


def render_value(template: str, payload: str) -> str:
    """Render a value template against an MQTT-style payload. Any failure is a TemplateError."""
    variables: dict[str, Any] = {"value": payload}
    try:
        variables["value_json"] = json.loads(payload)
    except ValueError:
        pass  # StrictUndefined makes any use of value_json fail
    return _render(_compile(template), variables)
