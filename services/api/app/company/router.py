from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.company.schemas import CompanyBrief, CompanyOut, CompanyWrite
from app.company.service import get_my_company, search_companies, update_my_company
from app.core.auth import Principal, require_role
from app.core.db import get_session

router = APIRouter(tags=["company"])


@router.get("/companies/me", response_model=CompanyOut)
async def get_my_company_route(
    principal: Principal = Depends(require_role("employer")),
    session: AsyncSession = Depends(get_session),
) -> CompanyOut:
    return await get_my_company(session, principal)


@router.put("/companies/me", response_model=CompanyOut)
async def update_my_company_route(
    body: CompanyWrite,
    principal: Principal = Depends(require_role("employer")),
    session: AsyncSession = Depends(get_session),
) -> CompanyOut:
    return await update_my_company(session, principal, body)


@router.get("/companies", response_model=list[CompanyBrief])
async def search_companies_route(
    q: str = "",
    limit: int = 10,
    _: Principal = Depends(require_role("candidate")),
    session: AsyncSession = Depends(get_session),
) -> list[CompanyBrief]:
    """Поиск компании по названию — кандидат скрывает от неё свой профиль."""
    return await search_companies(session, q, limit)
