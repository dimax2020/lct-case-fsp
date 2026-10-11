from uuid import UUID

from fastapi import APIRouter, Depends

from app.assessment.schemas import AnswerIn, AttemptCreate, AttemptResult, AttemptView, DemoFinishIn, RunIn, RunOut
from app.core.auth import Principal, require_role
from app.core.errors import not_implemented

router = APIRouter(prefix="/assessment", tags=["assessment"])


@router.post("/attempts", response_model=AttemptView, status_code=201)
async def create_attempt(body: AttemptCreate, _: Principal = Depends(require_role("candidate"))) -> None:
    del body
    not_implemented()


@router.get("/attempts/{id}", response_model=AttemptView)
async def get_attempt(id: UUID, _: Principal = Depends(require_role("candidate"))) -> None:
    del id
    not_implemented()


@router.post("/attempts/{id}/answers", response_model=AttemptView)
async def save_answer(
    id: UUID,
    body: AnswerIn,
    _: Principal = Depends(require_role("candidate")),
) -> None:
    del id, body
    not_implemented()


@router.post("/run", response_model=RunOut)
async def run_code(body: RunIn, _: Principal = Depends(require_role("candidate"))) -> None:
    del body
    not_implemented()


@router.post("/attempts/{id}/finish", response_model=AttemptResult)
async def finish_attempt(id: UUID, _: Principal = Depends(require_role("candidate"))) -> None:
    del id
    not_implemented()


@router.post("/attempts/{id}/demo-finish", response_model=AttemptResult)
async def demo_finish_attempt(
    id: UUID,
    body: DemoFinishIn,
    _: Principal = Depends(require_role("admin")),
) -> None:
    del id, body
    not_implemented()
