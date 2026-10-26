from dataclasses import dataclass
from typing import Literal

from cave.auth.users import Role

ItemKind = Literal["dashboard", "section", "action", "feature"]
Status = Literal["enabled", "disabled"]
Visibility = Literal["show", "hide", "restrict"]
OthersSee = Literal["locked", "none"]
NetworkCond = Literal["anywhere", "local"]
TargetKind = Literal["user", "group", "role", "screen"]
Purpose = Literal["use", "manage"]


@dataclass(frozen=True)
class Item:
    id: str
    kind: ItemKind
    name: str
    status: Status = "enabled"
    visibility: Visibility = "restrict"
    others_see: OthersSee = "locked"
    network: NetworkCond = "anywhere"
    builtin: bool = False


@dataclass(frozen=True)
class Principal:
    """Who is asking. A token carries its owner's user_id, role and groups."""

    kind: Literal["user", "screen", "token"]
    id: str
    user_id: str | None
    role: Role | None
    group_ids: frozenset[str]
    active: bool

    @property
    def is_admin(self) -> bool:
        return self.role == "admin" and self.kind != "screen"


@dataclass(frozen=True)
class Decision:
    allowed: bool
    listed: bool
