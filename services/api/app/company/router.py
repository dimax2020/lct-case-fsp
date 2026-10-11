from fastapi import APIRouter, Depends

from app.company.schemas import CompanyOut, CompanyWrite
from app.core.auth import Principal, require_role
from app.core.errors import not_implemented

router = APIRouter(tags=["company"])


@router.get("/companies/me", response_model=CompanyOut)
async def get_my_company(_: Principal = Depends(require_role("employer"))) -> None:
    not_implemented()


@router.put("/companies/me", response_model=CompanyOut)
async def update_my_company(body: CompanyWrite, _: Principal = Depends(require_role("employer"))) -> None:
    del body
    not_implemented()
