from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.auth import Principal, require_role
from app.core.errors import not_implemented
from app.need.schemas import (
    CandidateCard,
    MatchAccepted,
    NeedOut,
    NeedWrite,
    ParseResult,
    ShortlistOut,
)

router = APIRouter(tags=["needs"])


@router.get("/needs", response_model=list[NeedOut])
async def list_needs(_: Principal = Depends(require_role("employer"))) -> None:
    not_implemented()


@router.post("/needs", response_model=NeedOut, status_code=201)
async def create_need(body: NeedWrite, _: Principal = Depends(require_role("employer"))) -> None:
    del body
    not_implemented()


@router.get("/needs/{id}", response_model=NeedOut)
async def get_need(id: UUID, _: Principal = Depends(require_role("employer"))) -> None:
    del id
    not_implemented()


@router.put("/needs/{id}", response_model=NeedOut)
async def update_need(id: UUID, body: NeedWrite, _: Principal = Depends(require_role("employer"))) -> None:
    del id, body
    not_implemented()


@router.post("/needs/{id}/parse", response_model=ParseResult)
async def parse_need(id: UUID, _: Principal = Depends(require_role("employer"))) -> None:
    del id
    not_implemented()


@router.post("/needs/{id}/match", response_model=MatchAccepted, status_code=202)
async def match_need(id: UUID, _: Principal = Depends(require_role("employer"))) -> None:
    del id
    not_implemented()


@router.get("/needs/{id}/shortlist", response_model=ShortlistOut)
async def get_shortlist(
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
    _: Principal = Depends(require_role("employer")),
) -> None:
    del (
        id,
        category,
        only_fsp,
        fsp_discipline,
        min_test_score,
        stack,
        format,
        active_30d,
        tab,
        hint_id,
        page,
        page_size,
    )
    not_implemented()


@router.get("/needs/{id}/candidates/{candidate_id}", response_model=CandidateCard)
async def get_candidate_card(
    id: UUID,
    candidate_id: UUID,
    _: Principal = Depends(require_role("employer")),
) -> None:
    del id, candidate_id
    not_implemented()
