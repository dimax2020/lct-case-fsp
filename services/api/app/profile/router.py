from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

import app.profile.evidence  # noqa: F401  registers rebuild_evidence on the shared broker
import app.profile.storage as storage
from app.core.auth import Principal, require_role
from app.profile import daily as daily_tasks
from app.profile.bank import search_candidates
from app.profile.pdf import render_profile_pdf
from app.profile.schemas import (
    CandidateBankItem,
    CandidateProfile,
    CandidateSettings,
    CandidateUpdate,
    DailyTaskIn,
    DailyTaskView,
    GradeView,
    Me,
    ProjectIn,
    ProjectOut,
)
from app.profile.service import get_db

router = APIRouter(tags=["profile"])


async def _db() -> AsyncIterator[AsyncSession]:
    async for session in get_db():
        yield session


@router.get("/me", response_model=Me)
async def get_me(
    principal: Principal = Depends(require_role("candidate", "employer", "admin")),
    session: AsyncSession = Depends(_db),
) -> Me:
    return await storage.build_me(session, principal)


@router.get("/candidates/me", response_model=CandidateProfile)
async def get_my_candidate(
    principal: Principal = Depends(require_role("candidate")),
    session: AsyncSession = Depends(_db),
) -> CandidateProfile:
    candidate = await storage.current_candidate(session, principal)
    return await storage.profile_view(session, candidate)


@router.put("/candidates/me", response_model=CandidateProfile)
async def update_my_candidate(
    body: CandidateUpdate,
    principal: Principal = Depends(require_role("candidate")),
    session: AsyncSession = Depends(_db),
) -> CandidateProfile:
    candidate = await storage.current_candidate(session, principal)
    return await storage.update_profile(session, candidate, body)


@router.get("/candidates/me/projects", response_model=list[ProjectOut])
async def list_my_projects(
    principal: Principal = Depends(require_role("candidate")),
    session: AsyncSession = Depends(_db),
) -> list[ProjectOut]:
    candidate = await storage.current_candidate(session, principal)
    return await storage.list_projects(session, candidate)


@router.post("/candidates/me/projects", response_model=ProjectOut, status_code=201)
async def create_my_project(
    body: ProjectIn,
    principal: Principal = Depends(require_role("candidate")),
    session: AsyncSession = Depends(_db),
) -> ProjectOut:
    candidate = await storage.current_candidate(session, principal)
    return await storage.create_project(session, candidate, body)


@router.put("/candidates/me/projects/{id}", response_model=ProjectOut)
async def update_my_project(
    id: UUID,
    body: ProjectIn,
    principal: Principal = Depends(require_role("candidate")),
    session: AsyncSession = Depends(_db),
) -> ProjectOut:
    candidate = await storage.current_candidate(session, principal)
    return await storage.update_project(session, candidate, id, body)


@router.delete("/candidates/me/projects/{id}", status_code=204)
async def delete_my_project(
    id: UUID,
    principal: Principal = Depends(require_role("candidate")),
    session: AsyncSession = Depends(_db),
) -> Response:
    candidate = await storage.current_candidate(session, principal)
    await storage.delete_project(session, candidate, id)
    return Response(status_code=204)


@router.post("/candidates/me/fsp-link", response_model=CandidateProfile)
async def link_my_fsp(
    principal: Principal = Depends(require_role("candidate")),
    session: AsyncSession = Depends(_db),
) -> CandidateProfile:
    candidate = await storage.current_candidate(session, principal)
    return await storage.link_fsp(session, candidate)


@router.delete("/candidates/me/fsp-link", response_model=CandidateProfile)
async def unlink_my_fsp(
    principal: Principal = Depends(require_role("candidate")),
    session: AsyncSession = Depends(_db),
) -> CandidateProfile:
    """Отвязать ФСП ID: достижения и навыки из реестра ФСП удаляются из профиля."""
    candidate = await storage.current_candidate(session, principal)
    return await storage.unlink_fsp(session, candidate)


@router.get("/candidates/me/daily-task", response_model=DailyTaskView)
async def get_my_daily_task(
    principal: Principal = Depends(require_role("candidate")),
    session: AsyncSession = Depends(_db),
) -> DailyTaskView:
    candidate = await storage.current_candidate(session, principal)
    return await daily_tasks.current_task(session, candidate)


@router.post("/candidates/me/daily-task", response_model=DailyTaskView)
async def answer_my_daily_task(
    body: DailyTaskIn,
    principal: Principal = Depends(require_role("candidate")),
    session: AsyncSession = Depends(_db),
) -> DailyTaskView:
    candidate = await storage.current_candidate(session, principal)
    return await daily_tasks.answer_task(session, candidate, body)


@router.get("/candidates/me/grade", response_model=GradeView)
async def get_my_grade(
    principal: Principal = Depends(require_role("candidate")),
    session: AsyncSession = Depends(_db),
) -> GradeView:
    candidate = await storage.current_candidate(session, principal)
    return await storage.grade_view(session, candidate)


@router.get("/candidates/me/settings", response_model=CandidateSettings)
async def get_my_settings(
    principal: Principal = Depends(require_role("candidate")),
    session: AsyncSession = Depends(_db),
) -> CandidateSettings:
    candidate = await storage.current_candidate(session, principal)
    return await storage.settings_full(session, candidate)


@router.put("/candidates/me/settings", response_model=CandidateSettings)
async def update_my_settings(
    body: CandidateSettings,
    principal: Principal = Depends(require_role("candidate")),
    session: AsyncSession = Depends(_db),
) -> CandidateSettings:
    candidate = await storage.current_candidate(session, principal)
    await storage.update_settings(session, candidate, body)
    return await storage.settings_full(session, candidate)


@router.get("/candidates/me/profile.pdf")
async def download_my_profile_pdf(
    principal: Principal = Depends(require_role("candidate")),
    session: AsyncSession = Depends(_db),
) -> Response:
    candidate = await storage.current_candidate(session, principal)
    profile = await storage.profile_view(session, candidate)
    payload = render_profile_pdf(profile)
    return Response(
        content=payload,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="profile.pdf"'},
    )


@router.get("/candidates", response_model=list[CandidateBankItem])
async def search_candidate_bank(
    specialization: str | None = None,
    grade: str | None = None,
    stack: str | None = None,
    fsp: bool | None = None,
    q: str | None = None,
    principal: Principal = Depends(require_role("employer")),
    session: AsyncSession = Depends(_db),
) -> list[CandidateBankItem]:
    company_id = await storage.employer_company_id(session, principal)
    return await search_candidates(
        session,
        company_id=company_id,
        specialization=specialization,
        grade=grade,
        stack=stack,
        fsp=fsp,
        q=q,
    )
