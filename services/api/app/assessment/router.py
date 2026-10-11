from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment import blueprint, micro, roadmap, service
from app.assessment.schemas import (
    AnswerIn,
    AttemptCreate,
    AttemptResult,
    AttemptView,
    BlueprintOut,
    DemoFinishIn,
    EligibilityOut,
    MicroAnswerIn,
    MicroAnswerOut,
    MicroTaskCreate,
    MicroTaskOut,
    RetakeIn,
    RoadmapChecksIn,
    RoadmapConcreteIn,
    RoadmapCreate,
    RoadmapLatest,
    RoadmapView,
    RunIn,
    RunOut,
)
from app.core.auth import Principal, require_role
from app.core.db import get_session
from app.core.provision import provision_user

router = APIRouter(prefix="/assessment", tags=["assessment"])


@router.get("/eligibility", response_model=EligibilityOut, include_in_schema=False)
async def eligibility(
    principal: Principal = Depends(require_role("candidate")),
    session: AsyncSession = Depends(get_session),
) -> EligibilityOut:
    return await service.get_eligibility(session, principal)


@router.get("/blueprint", response_model=BlueprintOut, include_in_schema=False)
async def need_blueprint(
    need_id: UUID,
    principal: Principal = Depends(require_role("employer")),
    session: AsyncSession = Depends(get_session),
) -> BlueprintOut:
    user = await provision_user(session, principal)
    found = await session.execute(
        text("SELECT id FROM companies WHERE owner_user_id = :uid"),
        {"uid": str(user.id)},
    )
    company_id = found.scalar_one_or_none()
    return await blueprint.blueprint_for_need(session, company_id, need_id)


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
@router.get("/roadmap/latest", response_model=RoadmapLatest, include_in_schema=False)
async def roadmap_latest(
    principal: Principal = Depends(require_role("candidate")),
    session: AsyncSession = Depends(get_session),
) -> RoadmapLatest:
    return await roadmap.latest(session, principal)


@router.post("/roadmap/runs", response_model=RoadmapView, status_code=201, include_in_schema=False)
async def roadmap_start(
    body: RoadmapCreate,
    principal: Principal = Depends(require_role("candidate")),
    session: AsyncSession = Depends(get_session),
) -> RoadmapView:
    return await roadmap.start_run(session, principal, body)


@router.get("/roadmap/runs/{id}", response_model=RoadmapView, include_in_schema=False)
async def roadmap_get(
    id: UUID,
    principal: Principal = Depends(require_role("candidate")),
    session: AsyncSession = Depends(get_session),
) -> RoadmapView:
    return await roadmap.get_run(session, principal, id)


@router.post("/roadmap/runs/{id}/checks", response_model=RoadmapView, include_in_schema=False)
async def roadmap_checks(
    id: UUID,
    body: RoadmapChecksIn,
    principal: Principal = Depends(require_role("candidate")),
    session: AsyncSession = Depends(get_session),
) -> RoadmapView:
    return await roadmap.save_checks(session, principal, id, body)


@router.post("/roadmap/runs/{id}/concrete", response_model=RoadmapView, include_in_schema=False)
async def roadmap_concrete(
    id: UUID,
    body: RoadmapConcreteIn,
    principal: Principal = Depends(require_role("candidate")),
    session: AsyncSession = Depends(get_session),
) -> RoadmapView:
    return await roadmap.save_concrete(session, principal, id, body)


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
