from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.company.schemas import CompanyOut, CompanyWrite
from app.company.service import get_my_company, update_my_company
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
