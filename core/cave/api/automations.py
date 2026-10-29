from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from cave import notifications
from cave.access.model import Principal
from cave.api.deps import current_principal, get_db

router = APIRouter(prefix="/api/v1")
Caller = Annotated[Principal, Depends(current_principal)]


def _person(p: Principal) -> str:
    if p.user_id is None:
        raise HTTPException(403, "Screens don't have notifications.")
    return p.user_id


class ReadBody(BaseModel):
    ids: list[int] = Field(max_length=1000)


@router.get("/notifications")
def get_notifications(request: Request, p: Caller, unread: bool = False) -> list[dict[str, Any]]:
    return notifications.list_for(get_db(request), _person(p), unread)


@router.post("/notifications/read", status_code=204)
def read_notifications(body: ReadBody, request: Request, p: Caller) -> None:
    notifications.mark_read(get_db(request), _person(p), body.ids)
