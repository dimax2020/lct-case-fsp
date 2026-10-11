from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, require_role
from app.core.db import get_session
from app.matching.service import ShortlistQuery
from app.need.schemas import (
    CandidateCard,
    MatchAccepted,
    NeedOut,
    NeedWrite,
    ParseResult,
    ShortlistOut,
)
from app.need.service import (
    create_need,
    enqueue_match,
    get_candidate_card,
    get_need,
    get_shortlist,
    list_needs,
    open_match_job,
    parse_need,
    update_need,
)

router = APIRouter(tags=["needs"])


@router.get("/needs", response_model=list[NeedOut])
async def list_needs_route(
    principal: Principal = Depends(require_role("employer")),
    session: AsyncSession = Depends(get_session),
) -> list[NeedOut]:
    rows = await list_needs(session, principal)
    await session.commit()
    return rows


@router.post("/needs", response_model=NeedOut, status_code=201)
async def create_need_route(
    body: NeedWrite,
    principal: Principal = Depends(require_role("employer")),
    session: AsyncSession = Depends(get_session),
) -> NeedOut:
    created = await create_need(session, principal, body)
    await session.commit()
    return created


@router.get("/needs/{id}", response_model=NeedOut)
async def get_need_route(
    id: UUID,
    principal: Principal = Depends(require_role("employer")),
    session: AsyncSession = Depends(get_session),
) -> NeedOut:
    return await get_need(session, principal, id)


@router.put("/needs/{id}", response_model=NeedOut)
async def update_need_route(
    id: UUID,
    body: NeedWrite,
    principal: Principal = Depends(require_role("employer")),
    session: AsyncSession = Depends(get_session),
) -> NeedOut:
    updated = await update_need(session, principal, id, body)
    await session.commit()
    return updated


@router.post("/needs/{id}/parse", response_model=ParseResult)
async def parse_need_route(
    id: UUID,
    principal: Principal = Depends(require_role("employer")),
    session: AsyncSession = Depends(get_session),
) -> ParseResult:
    parsed = await parse_need(session, principal, id)
    await session.commit()
    return parsed


@router.post("/needs/{id}/match", response_model=MatchAccepted, status_code=202)
async def match_need_route(
    id: UUID,
    principal: Principal = Depends(require_role("employer")),
    session: AsyncSession = Depends(get_session),
) -> MatchAccepted:
    job_id = await open_match_job(session, principal, id)
    await session.commit()
    await enqueue_match(id, job_id)
    return MatchAccepted(job_id=job_id)


@router.get("/needs/{id}/shortlist", response_model=ShortlistOut)
async def get_shortlist_route(
    id: UUID,
    category: str | None = None,
    only_fsp: bool = False,
    fsp_discipline: str | None = None,
    min_test_score: int | None = None,
    stack: str | None = None,
    format: str | None = None,
    active_30d: bool = False,
    tab: str = "pool",
    hint_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
    principal: Principal = Depends(require_role("employer")),
    session: AsyncSession = Depends(get_session),
) -> ShortlistOut:
    query = ShortlistQuery(
        category=category,
        only_fsp=only_fsp,
        fsp_discipline=fsp_discipline,
        min_test_score=min_test_score,
        stack=stack,
        work_format=format,
        active_30d=active_30d,
        tab=tab,
        hint_id=hint_id,
        page=page,
        page_size=page_size,
    )
    return await get_shortlist(session, principal, id, query)


@router.get("/needs/{id}/candidates/{candidate_id}", response_model=CandidateCard)
async def get_candidate_card_route(
    id: UUID,
    candidate_id: UUID,
    principal: Principal = Depends(require_role("employer")),
    session: AsyncSession = Depends(get_session),
) -> CandidateCard:
    return await get_candidate_card(session, principal, id, candidate_id)
