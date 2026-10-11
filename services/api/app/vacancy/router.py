from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, require_role
from app.core.db import get_session
from app.vacancy.schemas import ApplicationCreate, ApplicationList, ApplicationOut, DeclineIn, VacancyOut, VacancyWrite
from app.vacancy.service import (
    accept_application,
    apply_to_vacancy,
    create_vacancy,
    decline_application,
    get_vacancy,
    list_applications,
    list_vacancies,
    update_vacancy,
    view_application,
)

router = APIRouter(tags=["vacancies"])


@router.get("/vacancies", response_model=list[VacancyOut])
async def list_vacancies_route(
    specialization: str | None = None,
    grade: str | None = None,
    principal: Principal = Depends(require_role("candidate", "employer")),
    session: AsyncSession = Depends(get_session),
) -> list[VacancyOut]:
    return await list_vacancies(session, principal, specialization=specialization, grade=grade)


@router.post("/vacancies", response_model=VacancyOut, status_code=201)
async def create_vacancy_route(
    body: VacancyWrite,
    principal: Principal = Depends(require_role("employer")),
    session: AsyncSession = Depends(get_session),
) -> VacancyOut:
    return await create_vacancy(session, principal, body)


@router.get("/vacancies/{id}", response_model=VacancyOut)
async def get_vacancy_route(
    id: UUID,
    principal: Principal = Depends(require_role("candidate", "employer")),
    session: AsyncSession = Depends(get_session),
) -> VacancyOut:
    return await get_vacancy(session, principal, id)


@router.put("/vacancies/{id}", response_model=VacancyOut)
async def update_vacancy_route(
    id: UUID,
    body: VacancyWrite,
    principal: Principal = Depends(require_role("employer")),
    session: AsyncSession = Depends(get_session),
) -> VacancyOut:
    return await update_vacancy(session, principal, id, body)


@router.post("/vacancies/{id}/applications", response_model=ApplicationOut, status_code=201)
async def apply_route(
    id: UUID,
    body: ApplicationCreate,
    principal: Principal = Depends(require_role("candidate")),
    session: AsyncSession = Depends(get_session),
) -> ApplicationOut:
    return await apply_to_vacancy(session, principal, id, body)


@router.get("/applications", response_model=ApplicationList)
async def list_applications_route(
    role: str | None = None,
    principal: Principal = Depends(require_role("candidate", "employer")),
    session: AsyncSession = Depends(get_session),
) -> ApplicationList:
    return await list_applications(session, principal, role)


@router.post("/applications/{id}/view", response_model=ApplicationOut)
async def view_application_route(
    id: UUID,
    principal: Principal = Depends(require_role("employer")),
    session: AsyncSession = Depends(get_session),
) -> ApplicationOut:
    return await view_application(session, principal, id)


@router.post("/applications/{id}/accept", response_model=ApplicationOut)
async def accept_application_route(
    id: UUID,
    principal: Principal = Depends(require_role("employer")),
    session: AsyncSession = Depends(get_session),
) -> ApplicationOut:
    return await accept_application(session, principal, id)


@router.post("/applications/{id}/decline", response_model=ApplicationOut)
async def decline_application_route(
    id: UUID,
    body: DeclineIn,
    principal: Principal = Depends(require_role("employer")),
    session: AsyncSession = Depends(get_session),
) -> ApplicationOut:
    return await decline_application(session, principal, id, body)
