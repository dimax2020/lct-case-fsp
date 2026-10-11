from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, require_role
from app.core.db import get_session
from app.hints.schemas import CandidateHint, EmployerHint
from app.hints.service import candidate_id_for, recompute_candidate, recompute_employer, require_employer_need

router = APIRouter(tags=["hints"])


@router.get("/candidates/me/hints", response_model=list[CandidateHint])
async def get_my_hints(principal: Principal = Depends(require_role("candidate"))) -> list[CandidateHint]:
    candidate_id = await candidate_id_for(principal)
    if candidate_id is None:
        return []
    return [CandidateHint.model_validate(item) for item in await recompute_candidate(candidate_id)]


@router.get("/needs/{id}/hints", response_model=list[EmployerHint])
async def get_need_hints(
    id: UUID,
    principal: Principal = Depends(require_role("employer")),
    session: AsyncSession = Depends(get_session),
) -> list[EmployerHint]:
    await require_employer_need(session, principal, id)
    return [EmployerHint.model_validate(item) for item in await recompute_employer(id)]
