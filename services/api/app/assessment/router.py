from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment import micro, service
from app.assessment.schemas import (
    AnswerIn,
    AttemptCreate,
    AttemptResult,
    AttemptView,
    DemoFinishIn,
    MicroAnswerIn,
    MicroAnswerOut,
    MicroTaskCreate,
    MicroTaskOut,
    RetakeIn,
    RunIn,
    RunOut,
)
from app.core.auth import Principal, require_role
from app.core.db import get_session

router = APIRouter(prefix="/assessment", tags=["assessment"])


@router.post("/attempts", response_model=AttemptView, status_code=201)
async def create_attempt(
    body: AttemptCreate,
    principal: Principal = Depends(require_role("candidate")),
    session: AsyncSession = Depends(get_session),
) -> AttemptView:
    return await service.create_attempt(session, principal, body)


@router.get("/attempts/{id}", response_model=AttemptView)
async def get_attempt(
    id: UUID,
    principal: Principal = Depends(require_role("candidate")),
    session: AsyncSession = Depends(get_session),
) -> AttemptView:
    return await service.get_attempt(session, principal, id)


@router.post("/attempts/{id}/answers", response_model=AttemptView)
async def save_answer(
    id: UUID,
    body: AnswerIn,
    principal: Principal = Depends(require_role("candidate")),
    session: AsyncSession = Depends(get_session),
) -> AttemptView:
    return await service.save_answer(session, principal, id, body)


@router.post("/run", response_model=RunOut)
async def run_code(body: RunIn, _: Principal = Depends(require_role("candidate"))) -> RunOut:
    result = await service.run_code(body.task_id, body.code, body.language, False)
    return service.to_run_out(result)


@router.post("/attempts/{id}/finish", response_model=AttemptResult)
async def finish_attempt(
    id: UUID,
    principal: Principal = Depends(require_role("candidate")),
    session: AsyncSession = Depends(get_session),
) -> AttemptResult:
    return await service.finish_attempt(session, principal, id)


# Kept out of the generated schema until contracts/openapi.yaml lists these paths.
@router.post("/retake", response_model=AttemptView, status_code=201, include_in_schema=False)
async def retake(
    body: RetakeIn,
    principal: Principal = Depends(require_role("candidate")),
    session: AsyncSession = Depends(get_session),
) -> AttemptView:
    return await service.retake(session, principal, body)


@router.get("/micro-tasks", response_model=list[MicroTaskOut], include_in_schema=False)
async def list_micro_tasks(
    principal: Principal = Depends(require_role("candidate")),
    session: AsyncSession = Depends(get_session),
) -> list[MicroTaskOut]:
    return await micro.list_micro_tasks(session, principal)


@router.post("/micro-tasks", response_model=MicroTaskOut, status_code=201, include_in_schema=False)
async def create_micro_task(
    body: MicroTaskCreate,
    _: Principal = Depends(require_role("employer")),
    session: AsyncSession = Depends(get_session),
) -> MicroTaskOut:
    return await micro.create_micro_task(session, body)


@router.post("/micro-tasks/{id}/answer", response_model=MicroAnswerOut, status_code=201, include_in_schema=False)
async def answer_micro_task(
    id: UUID,
    body: MicroAnswerIn,
    principal: Principal = Depends(require_role("candidate")),
    session: AsyncSession = Depends(get_session),
) -> MicroAnswerOut:
    return await micro.answer_micro_task(session, principal, id, body)


@router.post("/attempts/{id}/demo-finish", response_model=AttemptResult)
async def demo_finish_attempt(
    id: UUID,
    body: DemoFinishIn,
    _: Principal = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> AttemptResult:
    return await service.demo_finish_attempt(session, id, body)
