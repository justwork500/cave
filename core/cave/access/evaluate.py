from collections.abc import Sequence

from cave.access.items import get_assignments
from cave.access.model import Decision, Item, Principal, Purpose
from cave.access.network import IPAddress, is_local
from cave.db import Database


def _assigned(db: Database, p: Principal, item: Item) -> bool:
    for kind, target in get_assignments(db, item.id):
        if (
            (kind == "user" and p.kind != "screen" and target == p.user_id)
            or (kind == "group" and target in p.group_ids)
            or (kind == "role" and p.role is not None and target == p.role)
            or (kind == "screen" and p.kind == "screen" and target == p.id)
        ):
            return True
    return False


def evaluate(
    db: Database,
    p: Principal,
    item: Item,
    client_ip: IPAddress,
    local_ranges: Sequence[str],
    purpose: Purpose = "use",
) -> Decision:
    """The one access decision. Steps follow the Phase 1 design's "Effective access" section."""
    if not p.active:
        return Decision(False, False)
    if p.is_admin:
        return Decision(purpose == "manage" or item.status == "enabled", True)
    assigned = item.visibility == "restrict" and _assigned(db, p, item)
    if item.status == "disabled":
        return Decision(False, item.visibility == "show" or assigned)
    # what an outsider is shown follows Visibility, even when the network check is what denies them
    listed = item.visibility == "show" or assigned or (item.visibility == "restrict" and item.others_see == "locked")
    if item.network == "local" and not is_local(client_ip, local_ranges):
        return Decision(False, listed)
    if item.visibility == "show":
        return Decision(True, True)
    return Decision(assigned, listed)
