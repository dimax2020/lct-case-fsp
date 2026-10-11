from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.auth import Principal, require_role
from app.core.errors import not_implemented
from app.invitation.schemas import DeclineIn, FavoriteOut, InvitationCreate, InvitationList, InvitationOut

router = APIRouter(tags=["invitations"])


@router.post("/favorites/{candidate_id}", response_model=FavoriteOut)
async def add_favorite(candidate_id: UUID, _: Principal = Depends(require_role("employer"))) -> None:
    del candidate_id
    not_implemented()


@router.delete("/favorites/{candidate_id}", response_model=FavoriteOut)
async def remove_favorite(candidate_id: UUID, _: Principal = Depends(require_role("employer"))) -> None:
    del candidate_id
    not_implemented()


@router.post("/invitations", response_model=InvitationOut, status_code=201)
async def create_invitation(
    body: InvitationCreate,
    _: Principal = Depends(require_role("employer")),
) -> None:
    del body
    not_implemented()


@router.get("/invitations", response_model=InvitationList)
async def list_invitations(
    role: str | None = None,
    status: str | None = None,
    _: Principal = Depends(require_role("candidate", "employer", "admin")),
) -> None:
    del role, status
    not_implemented()


@router.post("/invitations/{id}/view", response_model=InvitationOut)
async def view_invitation(id: UUID, _: Principal = Depends(require_role("candidate"))) -> None:
    del id
    not_implemented()


@router.post("/invitations/{id}/accept", response_model=InvitationOut)
async def accept_invitation(id: UUID, _: Principal = Depends(require_role("candidate"))) -> None:
    del id
    not_implemented()


@router.post("/invitations/{id}/decline", response_model=InvitationOut)
async def decline_invitation(
    id: UUID,
    body: DeclineIn,
    _: Principal = Depends(require_role("candidate")),
) -> None:
    del id, body
    not_implemented()


@router.post("/invitations/{id}/revoke", response_model=InvitationOut)
async def revoke_invitation(id: UUID, _: Principal = Depends(require_role("employer"))) -> None:
    del id
    not_implemented()


@router.post("/invitations/{id}/remind", response_model=InvitationOut)
async def remind_invitation(id: UUID, _: Principal = Depends(require_role("employer"))) -> None:
    del id
    not_implemented()
