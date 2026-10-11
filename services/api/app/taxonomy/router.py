from fastapi import APIRouter, Depends

from app.core.auth import Principal, get_principal
from app.core.errors import not_implemented
from app.taxonomy.schemas import DeclineReasonOut, DomainOut, SkillHit, SpecializationOut

router = APIRouter(prefix="/taxonomy", tags=["taxonomy"])


@router.get("/skills", response_model=list[SkillHit])
async def search_skills(q: str = "", limit: int = 10, _: Principal = Depends(get_principal)) -> None:
    del q, limit
    not_implemented()


@router.get("/specializations", response_model=list[SpecializationOut])
async def list_specializations(_: Principal = Depends(get_principal)) -> None:
    not_implemented()


@router.get("/domains", response_model=list[DomainOut])
async def list_domains(_: Principal = Depends(get_principal)) -> None:
    not_implemented()


@router.get("/decline-reasons", response_model=list[DeclineReasonOut])
async def list_decline_reasons(_: Principal = Depends(get_principal)) -> None:
    not_implemented()
