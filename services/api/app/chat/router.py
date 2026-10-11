from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.schemas import MessageCreate, MessageList, MessageOut
from app.chat.service import create_message, list_messages
from app.core.auth import Principal, require_role
from app.core.db import get_session

router = APIRouter(tags=["chat"])


@router.get("/invitations/{id}/messages", response_model=MessageList)
async def list_messages_route(
    id: UUID,
    after: datetime | None = None,
    principal: Principal = Depends(require_role("candidate", "employer")),
    session: AsyncSession = Depends(get_session),
) -> MessageList:
    return await list_messages(session, principal, id, after)


@router.post("/invitations/{id}/messages", response_model=MessageOut, status_code=201)
async def create_message_route(
    id: UUID,
    body: MessageCreate,
    principal: Principal = Depends(require_role("candidate", "employer")),
    session: AsyncSession = Depends(get_session),
) -> MessageOut:
    return await create_message(session, principal, id, body)
