"""What a document references: the entities it reads or controls, and the routines and scripts it uses."""

from dataclasses import dataclass
from typing import Any

from cave.config.models import (
    AndCondition,
    Automation,
    ButtonCard,
    Call,
    Choose,
    Dashboard,
    EntitiesCard,
    GaugeCard,
    MarkdownCard,
    MqttPublish,
    NotCondition,
    Notify,
    NumericStateCondition,
    NumericStateTrigger,
    OrCondition,
    Repeat,
    RunSequence,
    Script,
    Sequence,
    SetVariable,
    StateCondition,
    StateTrigger,
    TemplateCondition,
    TileCard,
    WaitFor,
)
from cave.templates import entity_refs


@dataclass(frozen=True)
class Refs:
    entities: frozenset[str]
    sequences: frozenset[str]
    automations: frozenset[str]
    scripts: frozenset[str]
    dynamic_template: bool


def refs(doc: Automation | Sequence | Dashboard) -> Refs:
    entities: set[str] = set()
    sequences: set[str] = set()
    automations: set[str] = set()
    scripts: set[str] = set()
    dynamic = False

    def template(value: Any) -> None:
        nonlocal dynamic
        if isinstance(value, str):
            found, dyn = entity_refs(value)
            entities.update(found)
            dynamic = dynamic or dyn
        elif isinstance(value, dict):
            for v in value.values():
                template(v)
        elif isinstance(value, list):
            for v in value:
                template(v)

    def walk(items: list[Any]) -> None:
        for x in items:
            if isinstance(x, StateTrigger | NumericStateTrigger | StateCondition | NumericStateCondition | WaitFor):
                entities.add(x.entity)
            elif isinstance(x, TemplateCondition):
                template(x.value)
            elif isinstance(x, AndCondition | OrCondition | NotCondition):
                walk(x.conditions)
            elif isinstance(x, Call):
                entities.add(x.target)
                template(x.args)
            elif isinstance(x, Notify):
                template([x.title, x.message])
            elif isinstance(x, Choose):
                for opt in x.options:
                    walk(opt.conditions)
                    walk(opt.actions)
                walk(x.default)
            elif isinstance(x, Repeat):
                walk(x.actions + (x.while_ or []) + (x.until or []))
            elif isinstance(x, RunSequence):
                sequences.add(x.ref.split(".", 1)[1])
                template(x.with_)
            elif isinstance(x, Script):
                scripts.add(x.ref)
                template(x.args)
            elif isinstance(x, SetVariable):
                template(x.value)
            elif isinstance(x, MqttPublish):
                template(x.payload)
            elif isinstance(x, TileCard | GaugeCard):
                entities.add(x.entity)
            elif isinstance(x, EntitiesCard):
                entities.update(x.entities)
            elif isinstance(x, ButtonCard):
                if x.entity:
                    entities.add(x.entity)
                if x.action:
                    kind, ident = x.action.split(".", 1)
                    (sequences if kind == "sequence" else automations).add(ident)
            elif isinstance(x, MarkdownCard):
                template(x.content)

    if isinstance(doc, Automation):
        walk([*doc.triggers, *doc.conditions, *doc.actions])
    elif isinstance(doc, Sequence):
        walk(list(doc.actions))
    else:
        walk([c for v in doc.views for s in v.sections for c in s.cards])
    return Refs(frozenset(entities), frozenset(sequences), frozenset(automations), frozenset(scripts), dynamic)
