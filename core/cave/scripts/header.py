"""The `cave:` header at the top of every script, and the parameter checks it drives."""

import json
import re
from collections.abc import Mapping
from datetime import timedelta
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cave.config.models import Duration, Ident
from cave.config.yamlfile import ConfigError, load_text, validate

Language = Literal["powershell", "python", "bash"]
FILE_NAME = re.compile(r"^(?!.*\.\.)[A-Za-z0-9_.-]{1,64}\.(ps1|py|sh)$")
LANGUAGES: dict[str, Language] = {"ps1": "powershell", "py": "python", "sh": "bash"}
MAX_TIMEOUT = timedelta(hours=1)
MAX_STR = 4096
TRUE, FALSE = {"true", "yes", "on", "1"}, {"false", "no", "off", "0"}


def language_of(file: str) -> Language:
    return LANGUAGES[file.rsplit(".", 1)[1]]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Param(_Strict):
    type: Literal["int", "float", "str", "bool"]
    default: Any = None
    min: float | None = None
    max: float | None = None
    choices: list[str] | None = None


class ScriptHeader(_Strict):
    name: str = Field(min_length=1, max_length=100)
    target: str = "sandbox"
    timeout: Duration = timedelta(seconds=60)
    params: dict[Ident, Param] = {}
    secrets: list[Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")]] = []
    sample: dict[str, Any] | None = None

    @field_validator("target")
    @classmethod
    def _sandbox_only(cls, v: str) -> str:
        if v != "sandbox":
            raise ValueError("only target: sandbox is available in this version (SSH and CAVE-host come later)")
        return v

    @field_validator("timeout")
    @classmethod
    def _hour_at_most(cls, v: timedelta) -> timedelta:
        if v > MAX_TIMEOUT or v <= timedelta(0):
            raise ValueError("a script's timeout is at most 1 hour")
        return v


class _File(_Strict):
    cave: ScriptHeader


def _extract(file: str, text: str) -> tuple[str, int]:
    """The header's YAML, and the file line it starts on (1-based)."""
    lines = text.splitlines()
    if file.endswith(".ps1"):
        for m in re.finditer(r"<#(.*?)#>", text, re.DOTALL):
            if next((ln.strip() for ln in m[1].splitlines() if ln.strip()), "") == "cave:":
                return m[1], text.count("\n", 0, m.start(1)) + 1
        raise ConfigError(file, "", "no `cave:` header (a <# … #> block starting with cave:)", 1)
    start = 1 if lines and lines[0].startswith("#!") else 0
    if start < len(lines) and re.match(r"^#\s?cave:\s*$", lines[start]):
        body = []
        for line in lines[start:]:
            if not line.startswith("#"):
                break
            body.append(line[2:] if line.startswith("# ") else line[1:])
        return "\n".join(body), start + 1
    raise ConfigError(file, "", "no `cave:` header (comment lines starting with # cave:)", start + 1)


def parse_header(file: str, text: str) -> ScriptHeader:
    yaml_text, first_line = _extract(file, text)
    try:
        doc = load_text(yaml_text, file)
        return validate(_File, doc, file).cave
    except ConfigError as e:
        line = e.line + first_line - 1 if e.line is not None else first_line
        raise ConfigError(file, e.path, e.reason, line) from e


def _convert(name: str, spec: Param, value: Any) -> Any:
    try:
        if spec.type == "bool":
            if isinstance(value, bool):
                return value
            word = str(value).strip().lower()
            if word in TRUE | FALSE:
                return word in TRUE
            raise ValueError
        if spec.type == "int":
            if isinstance(value, bool) or (isinstance(value, float) and not value.is_integer()):
                raise ValueError
            out: Any = int(value)
        elif spec.type == "float":
            if isinstance(value, bool):
                raise ValueError
            out = float(value)
        else:
            out = value if isinstance(value, str) else json.dumps(value)
            if len(out) > MAX_STR:
                raise ValueError(f"{name} is longer than {MAX_STR} characters")
    except (TypeError, ValueError) as e:
        raise ValueError(str(e) if str(e) else f"{name} must be a {spec.type}, not {value!r}") from e
    if spec.type in ("int", "float") and (
        (spec.min is not None and out < spec.min) or (spec.max is not None and out > spec.max)
    ):
        raise ValueError(f"{name} must be between {spec.min} and {spec.max}")
    if spec.choices is not None and str(out) not in spec.choices:
        raise ValueError(f"{name} must be one of {', '.join(spec.choices)}")
    return out


def check_args(header: ScriptHeader, args: Mapping[str, Any]) -> dict[str, Any]:
    """The trust boundary: only declared parameters, converted to their types, inside their limits."""
    for name in args:
        if name not in header.params:
            raise ValueError(f"unknown parameter: {name}")
    out: dict[str, Any] = {}
    for name, spec in header.params.items():
        if name in args:
            out[name] = _convert(name, spec, args[name])
        elif spec.default is not None:
            out[name] = _convert(name, spec, spec.default)
        else:
            raise ValueError(f"missing parameter: {name}")
    return out
