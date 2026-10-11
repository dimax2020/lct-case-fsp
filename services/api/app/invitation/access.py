"""Chat-facing invitation gate. No ORM imports, so other modules can depend on it."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.core.errors import AppError
from app.core.models import User
from app.core.provision import provision_user


@dataclass(frozen=True)
class ChatAccess:
    invitation_id: UUID
    need_id: UUID
    status: str
    candidate_user_id: UUID
    employer_user_id: UUID


def _uuid(value: object) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


async def current_user(session: AsyncSession, principal: Principal) -> User:
    user = await provision_user(session, principal)
    await session.commit()
    return user


async def require_chat(session: AsyncSession, invitation_id: UUID, user_id: UUID) -> ChatAccess:
    row = (
        (
            await session.execute(
                text(
                    """
                SELECT i.id, i.need_id, i.status,
                       ca.user_id AS candidate_user_id,
                       co.owner_user_id AS employer_user_id
                FROM invitations i
                JOIN needs n ON n.id = i.need_id
                JOIN companies co ON co.id = n.company_id
                JOIN candidates ca ON ca.id = i.candidate_id
                WHERE i.id = :id
                """
                ),
                {"id": invitation_id},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise AppError("not_found", "Приглашение не найдено", status_code=404)
    access = ChatAccess(
        invitation_id=_uuid(row["id"]),
        need_id=_uuid(row["need_id"]),
        status=str(row["status"]),
        candidate_user_id=_uuid(row["candidate_user_id"]),
        employer_user_id=_uuid(row["employer_user_id"]),
    )
    if user_id not in {access.candidate_user_id, access.employer_user_id}:
        raise AppError("forbidden", "Недостаточно прав", status_code=403)
    if access.status != "accepted":
        raise AppError(
            "invitation_not_accepted",
            "Диалог доступен после принятия приглашения",
            status_code=409,
        )
    return access


async def set_hiring_stage(session: AsyncSession, invitation_id: UUID, stage: str) -> None:
    found = (await session.execute(text("SELECT status FROM invitations WHERE id = :id"), {"id": invitation_id})).first()
    if found is None:
        raise AppError("not_found", "Приглашение не найдено", status_code=404)
    if str(found[0]) != "accepted":
        raise AppError(
            "invitation_not_accepted",
            "Диалог доступен после принятия приглашения",
            status_code=409,
        )
    await session.execute(
        text("UPDATE invitations SET hiring_stage = :stage WHERE id = :id"),
        {"id": invitation_id, "stage": stage},
    )
