"""Messages on an accepted invitation."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.models import Message
from app.chat.schemas import MessageCreate, MessageList, MessageOut, Slot
from app.core.auth import Principal
from app.core.enums import HiringStage, MessageKind
from app.core.errors import AppError
from app.invitation.access import current_user, require_chat, set_hiring_stage


def _message_out(row: Message) -> MessageOut:
    slots = [Slot.model_validate(item) for item in row.slots] if row.slots else None
    stage = HiringStage(row.hiring_stage) if row.hiring_stage else None
    return MessageOut(
        id=row.id,
        author_user_id=row.author_user_id,
        kind=MessageKind(row.kind),
        body=row.body or "",
        slots=slots,
        hiring_stage=stage,
        created_at=row.created_at,
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


async def list_messages(
    session: AsyncSession,
    principal: Principal,
    invitation_id: UUID,
    after: datetime | None,
) -> MessageList:
    user = await current_user(session, principal)
    access = await require_chat(session, invitation_id, user.id)
    stmt = select(Message).where(Message.invitation_id == access.invitation_id)
    if after is not None:
        stmt = stmt.where(Message.created_at > _as_utc(after))
    stmt = stmt.order_by(Message.created_at.asc(), Message.id.asc())
    rows = list(await session.scalars(stmt))
    return MessageList(items=[_message_out(row) for row in rows])


async def create_message(
    session: AsyncSession,
    principal: Principal,
    invitation_id: UUID,
    body: MessageCreate,
) -> MessageOut:
    user = await current_user(session, principal)
    access = await require_chat(session, invitation_id, user.id)
    if body.hiring_stage is not None and user.id != access.employer_user_id:
        raise AppError("forbidden", "Этап найма задаёт работодатель", status_code=403)
    if body.kind == MessageKind.text and not body.body.strip():
        raise AppError("validation_error", "Пустое сообщение", status_code=422)
    if body.kind == MessageKind.slots and not body.slots:
        raise AppError("validation_error", "Укажите слоты интервью", status_code=422)
    if body.slots:
        for slot in body.slots:
            if slot.end <= slot.start:
                raise AppError("validation_error", "Конец слота должен быть позже начала", status_code=422)
    slots = None
    if body.kind == MessageKind.slots and body.slots:
        slots = [slot.model_dump(mode="json") for slot in body.slots]
    stage = body.hiring_stage.value if body.hiring_stage is not None else None
    message = Message(
        invitation_id=access.invitation_id,
        author_user_id=user.id,
        kind=body.kind.value,
        body=body.body,
        slots=slots,
        hiring_stage=stage,
        created_at=datetime.now(UTC),
    )
    session.add(message)
    if stage is not None:
        await set_hiring_stage(session, access.invitation_id, stage)
    await session.commit()
    await session.refresh(message)
    return _message_out(message)
