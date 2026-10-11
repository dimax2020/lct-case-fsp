from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends

from app.chat.schemas import MessageCreate, MessageList, MessageOut
from app.core.auth import Principal, require_role
from app.core.errors import not_implemented

router = APIRouter(tags=["chat"])


@router.get("/invitations/{id}/messages", response_model=MessageList)
async def list_messages(
    id: UUID,
    after: datetime | None = None,
    _: Principal = Depends(require_role("candidate", "employer")),
) -> None:
    del id, after
    not_implemented()


@router.post("/invitations/{id}/messages", response_model=MessageOut, status_code=201)
async def create_message(
    id: UUID,
    body: MessageCreate,
    _: Principal = Depends(require_role("candidate", "employer")),
) -> None:
    del id, body
    not_implemented()
