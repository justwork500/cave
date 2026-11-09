"""The YAML shapes for automations, sequences (routines) and dashboards. Unknown keys always fail."""

import re
from datetime import time, timedelta
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator

from cave.config.yamlfile import ConfigError, YamlDoc

MAX_DURATION = timedelta(hours=24)
MAX_NESTING = 8
ENTITY_ID = r"^[a-z_]+\.[a-z0-9_]+$"
IDENT = r"^[A-Za-z_][A-Za-z0-9_]{0,63}$"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


def _duration(v: Any) -> timedelta:
    # YAML 1.1 reads an unquoted 00:02:00 as the number 120 (base 60), so plain numbers are seconds
    if isinstance(v, timedelta):
        d = v
    elif isinstance(v, int | float) and not isinstance(v, bool):
        d = timedelta(seconds=v)
    elif isinstance(v, str) and (m := re.fullmatch(r"(\d+)\s*([smh])", v.strip())):
        d = timedelta(**{{"s": "seconds", "m": "minutes", "h": "hours"}[m[2]]: int(m[1])})
    elif isinstance(v, str) and re.fullmatch(r"\d+(:\d{1,2}){0,2}", v.strip()):
        parts = [int(p) for p in v.strip().split(":")]
        while len(parts) < 3:
            parts.insert(0, 0)
        d = timedelta(hours=parts[0], minutes=parts[1], seconds=parts[2])
    else:
        raise ValueError("expected seconds, HH:MM:SS, or a number with s, m or h")
    if d < timedelta(0) or d > MAX_DURATION:
        raise ValueError("durations are at most 24 hours")
    return d


def _clock(v: Any) -> time:
    # an unquoted 07:30 arrives as 450, the minutes since midnight
    if isinstance(v, int) and not isinstance(v, bool) and 0 <= v < 24 * 60:
        return time(v // 60, v % 60)
    if isinstance(v, str) and (m := re.fullmatch(r"(\d{1,2}):(\d{2})", v.strip())):
        h, mi = int(m[1]), int(m[2])
        if h < 24 and mi < 60:
            return time(h, mi)
    raise ValueError("expected a time like 07:30")


Duration = Annotated[timedelta, BeforeValidator(_duration)]
Clock = Annotated[time, BeforeValidator(_clock)]
EntityId = Annotated[str, Field(pattern=ENTITY_ID)]
Ident = Annotated[str, Field(pattern=IDENT)]
FileId = Annotated[str, Field(pattern=r"^[a-z0-9_-]{1,64}$")]
Weekday = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


# ---- triggers ----

class StateTrigger(_Strict):
    type: Literal["state"]
    entity: EntityId
    from_: str | None = Field(default=None, alias="from")
    to: str | None = None
    for_: Duration | None = Field(default=None, alias="for")


class NumericStateTrigger(_Strict):
    type: Literal["numeric_state"]
    entity: EntityId
    above: float | None = None
    below: float | None = None
    for_: Duration | None = Field(default=None, alias="for")

    @model_validator(mode="after")
    def _range(self) -> "NumericStateTrigger":
        if self.above is None and self.below is None:
            raise ValueError("needs above, below or both")
        return self


class TimeTrigger(_Strict):
    type: Literal["time"]
    at: Clock


class TimePatternTrigger(_Strict):
    type: Literal["time_pattern"]
    minutes: int | str = "*"
    hours: int | str = "*"

    @model_validator(mode="after")
    def _pattern(self) -> "TimePatternTrigger":
        for name, v, top in (("minutes", self.minutes, 59), ("hours", self.hours, 23)):
            ok = (isinstance(v, int) and 0 <= v <= top) or v == "*" or (
                isinstance(v, str) and re.fullmatch(r"/\d+", v) is not None and 0 < int(v[1:]) <= top + 1)
            if not ok:
                raise ValueError(f"{name} must be a number, '*' or '/N'")
        return self


class StartupTrigger(_Strict):
    type: Literal["startup"]


Trigger = Annotated[
    StateTrigger | NumericStateTrigger | TimeTrigger | TimePatternTrigger | StartupTrigger,
    Field(discriminator="type"),
]


# ---- conditions ----

class StateCondition(_Strict):
    type: Literal["state"]
    entity: EntityId
    state: str | list[str]


class NumericStateCondition(_Strict):
    type: Literal["numeric_state"]
    entity: EntityId
    above: float | None = None
    below: float | None = None


class TimeCondition(_Strict):
    type: Literal["time"]
    after: Clock | None = None
    before: Clock | None = None
    weekdays: list[Weekday] | None = None


class TemplateCondition(_Strict):
    type: Literal["template"]
    value: str


class AndCondition(_Strict):
    type: Literal["and"]
    conditions: "list[Condition]"


class OrCondition(_Strict):
    type: Literal["or"]
    conditions: "list[Condition]"


class NotCondition(_Strict):
    type: Literal["not"]
    conditions: "list[Condition]"


Condition = Annotated[
    StateCondition | NumericStateCondition | TimeCondition | TemplateCondition | AndCondition | OrCondition
    | NotCondition,
    Field(discriminator="type"),
]


# ---- actions ----

class Call(_Strict):
    type: Literal["call"]
    target: EntityId
    command: Ident
    args: dict[str, Any] = {}


class Notify(_Strict):
    type: Literal["notify"]
    targets: list[Annotated[str, Field(pattern=r"^(notify\.cave|user:.+)$")]] = []
    title: str | None = None
    message: str


class Delay(_Strict):
    type: Literal["delay"]
    duration: Duration


class WaitFor(_Strict):
    type: Literal["wait_for"]
    entity: EntityId
    to: str
    timeout: Duration
    on_timeout: Literal["stop", "continue"] = "stop"


class ChooseOption(_Strict):
    conditions: list[Condition]
    actions: "list[Action]"


class Choose(_Strict):
    type: Literal["choose"]
    options: list[ChooseOption]
    default: "list[Action]" = []


class Repeat(_Strict):
    type: Literal["repeat"]
    count: Annotated[int, Field(ge=1, le=1000)] | None = None
    while_: list[Condition] | None = Field(default=None, alias="while")
    until: list[Condition] | None = None
    actions: "list[Action]"

    @model_validator(mode="after")
    def _one_mode(self) -> "Repeat":
        if sum(x is not None for x in (self.count, self.while_, self.until)) != 1:
            raise ValueError("repeat needs exactly one of count, while or until")
        return self


class RunSequence(_Strict):
    type: Literal["sequence"]
    ref: Annotated[str, Field(pattern=r"^sequence\.[a-z0-9_-]{1,64}$")]
    with_: dict[str, Any] = Field(default={}, alias="with")


class Script(_Strict):
    type: Literal["script"]
    ref: str = Field(pattern=r"^scripts/[A-Za-z0-9_.-]{1,64}\.(ps1|py|sh)$")
    target: str | None = None
    args: dict[str, Any] = {}
    result_var: Ident | None = None

    @field_validator("ref")
    @classmethod
    def _no_dotdot(cls, v: str) -> str:
        if ".." in v:
            raise ValueError("script names can't contain ..")
        return v


class SetVariable(_Strict):
    type: Literal["set_variable"]
    name: Ident
    value: Any


class Stop(_Strict):
    type: Literal["stop"]
    reason: str | None = None


class MqttPublish(_Strict):
    type: Literal["mqtt_publish"]
    topic: Annotated[str, Field(min_length=1, pattern=r"^[^+#]+$")]
    payload: str
    retain: bool = False


Action = Annotated[
    Call | Notify | Delay | WaitFor | Choose | Repeat | RunSequence | Script | SetVariable | Stop | MqttPublish,
    Field(discriminator="type"),
]


# ---- documents ----

class Automation(_Strict):
    id: FileId
    name: str = Field(min_length=1, max_length=200)
    mode: Literal["single", "restart", "queued", "parallel"] = "single"
    max: Annotated[int, Field(ge=1, le=100)] = 10
    enabled: bool = True
    triggers: list[Trigger] = Field(min_length=1)
    conditions: list[Condition] = []
    actions: list[Action] = Field(min_length=1)


class SequenceField(_Strict):
    type: Literal["int", "float", "str", "bool"]
    default: Any = None


class Sequence(_Strict):
    id: FileId
    name: str = Field(min_length=1, max_length=200)
    fields: dict[Ident, SequenceField] = {}
    actions: list[Action] = Field(min_length=1)


CardIcon = Literal["lightbulb", "plug", "power", "wind", "fire", "temperature", "drop", "sun", "snow", "door", "lock",
                   "shield", "camera", "speaker", "tv", "home", "bed", "clock", "play", "battery"]
CardColor = Literal["blue", "green", "amber", "red", "purple"]
CardLabel = Annotated[str, Field(max_length=100)]


class _Card(_Strict):
    w: Annotated[int, Field(ge=1, le=12)] = 3
    h: Annotated[int, Field(ge=1, le=8)] = 1
    icon: CardIcon | None = None
    color: CardColor | None = None


class TileCard(_Card):
    type: Literal["tile"]
    entity: EntityId
    label: CardLabel | None = None
    tap_action: Literal["toggle", "none"] = "toggle"


class EntitiesCard(_Card):
    type: Literal["entities"]
    entities: list[EntityId]
    label: CardLabel | None = None


class GaugeCard(_Card):
    type: Literal["gauge"]
    entity: EntityId
    label: CardLabel | None = None
    min: float = 0
    max: float = 100
    severity: dict[str, float] | None = None


# the script branch is cave.scripts.header.FILE_NAME; Pydantic's patterns have no lookahead, so _target refuses ".."
BUTTON_ACTION = r"^(automation|sequence)\.[a-z0-9_-]{1,64}$|^script\.[A-Za-z0-9_.-]{1,64}\.(ps1|py|sh)$"


class ButtonCard(_Card):
    type: Literal["button"]
    name: str = Field(min_length=1, max_length=100)
    action: Annotated[str, Field(pattern=BUTTON_ACTION)] | None = None
    entity: EntityId | None = None
    command: Ident | None = None
    confirm: bool | None = None

    @model_validator(mode="after")
    def _target(self) -> "ButtonCard":
        if (self.action is None) == (self.entity is None or self.command is None):
            raise ValueError("a button needs either an action, or an entity and a command")
        if self.action and ".." in self.action:
            raise ValueError("a script name can't contain two dots in a row")
        return self


class MarkdownCard(_Card):
    type: Literal["markdown"]
    content: str = Field(max_length=10_000)


Card = Annotated[TileCard | EntitiesCard | GaugeCard | ButtonCard | MarkdownCard, Field(discriminator="type")]


class Section(_Strict):
    title: str
    cards: list[Card] = []


class View(_Strict):
    id: Annotated[str, Field(pattern=r"^[a-z0-9_-]{1,64}$")]
    title: str
    sections: list[Section] = []


class Dashboard(_Strict):
    title: str = Field(min_length=1, max_length=200)
    icon: str | None = None
    views: list[View] = []


class AutomationFile(_Strict):
    automation: Automation


class SequenceFile(_Strict):
    sequence: Sequence


class DashboardFile(_Strict):
    dashboard: Dashboard


for _m in (AndCondition, OrCondition, NotCondition, ChooseOption, Choose, Repeat, Automation, Sequence,
           AutomationFile, SequenceFile):
    _m.model_rebuild()


def check_nesting(doc: Automation | Sequence, yaml_doc: YamlDoc, file: str) -> None:
    """choose/repeat/and/or/not may nest at most MAX_NESTING deep."""
    root = "automation" if isinstance(doc, Automation) else "sequence"

    def walk(items: list[Any], loc: tuple[str | int, ...], depth: int) -> None:
        for i, item in enumerate(items):
            here = (*loc, i)
            children: list[tuple[list[Any], tuple[str | int, ...]]] = []
            if isinstance(item, Choose):
                for j, opt in enumerate(item.options):
                    children += [(opt.conditions, (*here, "options", j, "conditions")),
                                 (opt.actions, (*here, "options", j, "actions"))]
                children.append((item.default, (*here, "default")))
            elif isinstance(item, Repeat):
                children += [(item.actions, (*here, "actions")), (item.while_ or [], (*here, "while")),
                             (item.until or [], (*here, "until"))]
            elif isinstance(item, AndCondition | OrCondition | NotCondition):
                children.append((item.conditions, (*here, "conditions")))
            if children and depth >= MAX_NESTING:
                path = ".".join(str(p) for p in here)
                raise ConfigError(file, path, f"choose/repeat/and/or/not can nest at most {MAX_NESTING} deep",
                                  yaml_doc.lines.get(here))
            for sub, sub_loc in children:
                walk(sub, sub_loc, depth + 1)

    if isinstance(doc, Automation):
        walk(doc.conditions, (root, "conditions"), 0)
    walk(doc.actions, (root, "actions"), 0)


def schema_files() -> dict[str, dict[str, Any]]:
    return {
        "automation.json": AutomationFile.model_json_schema(by_alias=True),
        "sequence.json": SequenceFile.model_json_schema(by_alias=True),
        "dashboard.json": DashboardFile.model_json_schema(by_alias=True),
    }
