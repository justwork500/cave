"""YAML config files with a line map, so every validation error can say file:line."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

MAX_BYTES = 256 * 1024
Loc = tuple[str | int, ...]


class ConfigError(ValueError):
    def __init__(self, file: str, path: str, reason: str, line: int | None = None) -> None:
        self.file, self.path, self.reason, self.line = file, path, reason, line
        where = f"{file}:{line}" if line is not None else file
        super().__init__(f"{where}: {path}: {reason}" if path else f"{where}: {reason}")


@dataclass(frozen=True)
class YamlDoc:
    data: Any
    lines: Mapping[Loc, int]


def path_text(loc: Loc) -> str:
    out = ""
    for part in loc:
        out += f"[{part}]" if isinstance(part, int) else (f".{part}" if out else str(part))
    return out


def _walk(node: yaml.Node, loc: Loc, lines: dict[Loc, int], file: str) -> Any:
    if isinstance(node, yaml.MappingNode):
        out: dict[Any, Any] = {}
        for key_node, value_node in node.value:
            key = _walk(key_node, loc, lines, file)
            lines[(*loc, key)] = key_node.start_mark.line + 1
            out[key] = _walk(value_node, (*loc, key), lines, file)
        return out
    if isinstance(node, yaml.SequenceNode):
        items = []
        for i, item in enumerate(node.value):
            lines[(*loc, i)] = item.start_mark.line + 1
            items.append(_walk(item, (*loc, i), lines, file))
        return items
    return _SCALARS.construct_object(node)


class _AliasRefusingComposer(yaml.SafeLoader):
    def compose_node(self, parent: yaml.Node | None, index: Any) -> yaml.Node | None:
        if self.check_event(yaml.AliasEvent):
            event = self.peek_event()  # type: ignore[no-untyped-call]
            raise yaml.MarkedYAMLError(None, None, "YAML anchors and aliases aren't supported", event.start_mark)
        event = self.peek_event()  # type: ignore[no-untyped-call]
        if getattr(event, "anchor", None):
            raise yaml.MarkedYAMLError(None, None, "YAML anchors and aliases aren't supported", event.start_mark)
        return super().compose_node(parent, index)


_SCALARS = yaml.SafeLoader("")  # constructs plain scalars (str, int, bool, null, …) the safe way


def load_text(text: str, file: str) -> YamlDoc:
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise ConfigError(file, "", "file too large (256 KiB at most)")
    loader = _AliasRefusingComposer(text)
    try:
        node = loader.get_single_node()
    except yaml.MarkedYAMLError as e:
        mark = e.problem_mark or e.context_mark
        raise ConfigError(file, "", e.problem or str(e), mark.line + 1 if mark else None) from e
    except yaml.YAMLError as e:
        raise ConfigError(file, "", str(e)) from e
    finally:
        loader.dispose()
    lines: dict[Loc, int] = {}
    data = None if node is None else _walk(node, (), lines, file)
    return YamlDoc(data, lines)


def load_file(path: Path) -> YamlDoc:
    if path.stat().st_size > MAX_BYTES:
        raise ConfigError(path.name, "", "file too large (256 KiB at most)")
    return load_text(path.read_text(encoding="utf-8"), path.name)


def _line_for(loc: Loc, lines: Mapping[Loc, int]) -> int | None:
    for n in range(len(loc), -1, -1):
        if loc[:n] in lines:
            return lines[loc[:n]]
    return None


def _clean(loc: tuple[Any, ...], data: Any) -> Loc:
    """Drop Pydantic's discriminator segments (like 'call'), which aren't keys in the file."""
    out: list[str | int] = []
    node = data
    for part in loc:
        if isinstance(node, dict) and part in node or isinstance(node, list) and isinstance(part, int) and 0 <= part < len(node):
            node = node[part]
        elif isinstance(node, dict) and node.get("type") == part:
            continue  # the discriminator tag
        else:
            node = None  # an unknown or missing key: keep it, stop descending
        out.append(part)
    return tuple(out)


def validate[M: BaseModel](model: type[M], doc: YamlDoc, file: str) -> M:
    try:
        return model.model_validate(doc.data)
    except ValidationError as e:
        # a typo shows up as both "unknown key" and "missing key"; the unknown one is the useful message
        first = min(e.errors(), key=lambda err: err["type"] != "extra_forbidden")
        loc = _clean(first["loc"], doc.data)
        raise ConfigError(file, path_text(loc), first["msg"], _line_for(loc, doc.lines)) from e
