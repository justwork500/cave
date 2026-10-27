"""Sandboxed Jinja for value templates. Templates come from devices and other untrusted sources."""

import json
import operator
from functools import lru_cache
from typing import Any

from jinja2 import StrictUndefined, Template
from jinja2 import TemplateError as JinjaError
from jinja2.sandbox import ImmutableSandboxedEnvironment

MAX_REPEAT = 10_000  # longest string or list a template may build with `*`
MAX_EXPONENT = 64


class TemplateError(Exception):
    pass


class _Env(ImmutableSandboxedEnvironment):
    intercepted_binops = frozenset({"*", "**"})

    def call_binop(self, context: Any, operator_name: str, left: Any, right: Any) -> Any:
        # The sandbox blocks attribute tricks but not `'x' * 10**9`; cap the operators that can blow up memory.
        if operator_name == "**":
            if isinstance(right, int | float) and abs(right) > MAX_EXPONENT:
                raise TemplateError("exponent too large")
            return operator.pow(left, right)
        for seq, n in ((left, right), (right, left)):
            if isinstance(seq, str | list | tuple) and isinstance(n, int) and n > MAX_REPEAT:
                raise TemplateError("result too large")
        return operator.mul(left, right)


_ENV = _Env(autoescape=False, undefined=StrictUndefined)


@lru_cache(maxsize=512)
def _compile(source: str) -> Template:
    return _ENV.from_string(source)


def render_value(template: str, payload: str) -> str:
    """Render a value template against an MQTT-style payload. Any failure is a TemplateError."""
    variables: dict[str, Any] = {"value": payload}
    try:
        variables["value_json"] = json.loads(payload)
    except ValueError:
        pass  # StrictUndefined makes any use of value_json fail
    try:
        return str(_compile(template).render(variables))
    except TemplateError:
        raise
    except (JinjaError, ArithmeticError, TypeError, ValueError, RecursionError, MemoryError) as e:
        raise TemplateError(str(e)) from e
