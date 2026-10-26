from dataclasses import replace
from ipaddress import ip_address

from cave.access.model import Item, Principal

LAN = ip_address("192.168.1.5")
WAN = ip_address("203.0.113.9")
LOCAL = ["192.168.1.0/24"]


def user(uid: str, role: str = "household", groups: frozenset[str] = frozenset(), active: bool = True) -> Principal:
    return Principal(kind="user", id=uid, user_id=uid, role=role, group_ids=groups, active=active)  # type: ignore[arg-type]


def screen(sid: str) -> Principal:
    return Principal(kind="screen", id=sid, user_id=None, role=None, group_ids=frozenset(), active=True)


def token_of(p: Principal) -> Principal:
    return replace(p, kind="token", id="tok1")


PRINCIPALS = {
    "sam": user("sam", groups=frozenset({"family"})),
    "sam_disabled": user("sam", groups=frozenset({"family"}), active=False),
    "garage_tablet": screen("garage"),
    "other_tablet": screen("other"),
    "admin": user("root", role="admin"),
}


def item(**overrides: object) -> Item:
    return Item(id="dashboard:test", kind="dashboard", name="Test", **overrides)  # type: ignore[arg-type]
