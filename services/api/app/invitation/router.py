from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

import app.invitation.tasks as invitation_tasks  # noqa: F401
from app.core.auth import Principal, require_role
from app.core.db import get_session
from app.invitation.schemas import DeclineIn, FavoriteOut, InvitationCreate, InvitationList, InvitationOut
from app.invitation.service import (
    accept_invitation,
    add_favorite,
    create_invitation,
    decline_invitation,
    list_invitations,
    remind_invitation,
    remove_favorite,
    revoke_invitation,
    view_invitation,
)

router = APIRouter(tags=["invitations"])


@router.post("/favorites/{candidate_id}", response_model=FavoriteOut)
async def add_favorite_route(
    candidate_id: UUID,
    principal: Principal = Depends(require_role("employer")),
    session: AsyncSession = Depends(get_session),
) -> FavoriteOut:
    return await add_favorite(session, principal, candidate_id)


@router.delete("/favorites/{candidate_id}", response_model=FavoriteOut)
async def remove_favorite_route(
    candidate_id: UUID,
    principal: Principal = Depends(require_role("employer")),
    session: AsyncSession = Depends(get_session),
) -> FavoriteOut:
    return await remove_favorite(session, principal, candidate_id)


@router.post("/invitations", response_model=InvitationOut, status_code=201, response_model_exclude_none=True)
async def create_invitation_route(
    body: InvitationCreate,
    principal: Principal = Depends(require_role("employer")),
    session: AsyncSession = Depends(get_session),
) -> InvitationOut:
    return await create_invitation(session, principal, body)


@router.get("/invitations", response_model=InvitationList, response_model_exclude_none=True)
async def list_invitations_route(
    role: str | None = None,
    status: str | None = None,
    principal: Principal = Depends(require_role("candidate", "employer", "admin")),
    session: AsyncSession = Depends(get_session),
) -> InvitationList:
    return await list_invitations(session, principal, role=role, status=status)


@router.post("/invitations/{id}/view", response_model=InvitationOut, response_model_exclude_none=True)
async def view_invitation_route(
    id: UUID,
    principal: Principal = Depends(require_role("candidate")),
    session: AsyncSession = Depends(get_session),
) -> InvitationOut:
    return await view_invitation(session, principal, id)


@router.post("/invitations/{id}/accept", response_model=InvitationOut, response_model_exclude_none=True)
async def accept_invitation_route(
    id: UUID,
    principal: Principal = Depends(require_role("candidate")),
    session: AsyncSession = Depends(get_session),
) -> InvitationOut:
    return await accept_invitation(session, principal, id)


@router.post("/invitations/{id}/decline", response_model=InvitationOut, response_model_exclude_none=True)
async def decline_invitation_route(
    id: UUID,
    body: DeclineIn,
    principal: Principal = Depends(require_role("candidate")),
    session: AsyncSession = Depends(get_session),
) -> InvitationOut:
    return await decline_invitation(session, principal, id, body)


@router.post("/invitations/{id}/revoke", response_model=InvitationOut, response_model_exclude_none=True)
async def revoke_invitation_route(
    id: UUID,
    principal: Principal = Depends(require_role("employer")),
    session: AsyncSession = Depends(get_session),
) -> InvitationOut:
    return await revoke_invitation(session, principal, id)


@router.post("/invitations/{id}/remind", response_model=InvitationOut, response_model_exclude_none=True)
async def remind_invitation_route(
    id: UUID,
    principal: Principal = Depends(require_role("employer")),
    session: AsyncSession = Depends(get_session),
) -> InvitationOut:
    return await remind_invitation(session, principal, id)
