from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.auth import Principal, require_role
from app.core.errors import not_implemented
from app.demo.schemas import JobOut, ReseedOut
from app.demo.service import reseed as reseed_demo

router = APIRouter(tags=["demo"])


@router.get("/jobs/{id}", response_model=JobOut)
async def get_job(id: UUID, _: Principal = Depends(require_role("candidate", "employer", "admin"))) -> None:
    del id
    not_implemented()


@router.post("/demo/reseed", response_model=ReseedOut)
async def reseed(_: Principal = Depends(require_role("admin"))) -> ReseedOut:
    counts = await reseed_demo()
    return ReseedOut(**counts)
