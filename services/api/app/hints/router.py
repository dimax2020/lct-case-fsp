from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.auth import Principal, require_role
from app.core.errors import not_implemented
from app.hints.schemas import CandidateHint, EmployerHint

router = APIRouter(tags=["hints"])


@router.get("/candidates/me/hints", response_model=list[CandidateHint])
async def get_my_hints(_: Principal = Depends(require_role("candidate"))) -> None:
    not_implemented()


@router.get("/needs/{id}/hints", response_model=list[EmployerHint])
async def get_need_hints(id: UUID, _: Principal = Depends(require_role("employer"))) -> None:
    del id
    not_implemented()
