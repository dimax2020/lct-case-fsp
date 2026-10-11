from fastapi import APIRouter, Depends

from app.core.auth import Principal, get_principal
from app.taxonomy.schemas import DeclineReasonOut, DomainOut, SkillHit, SpecializationOut
from app.taxonomy.service import Skill, list_decline_reasons, list_domains, list_specializations, search_skills

router = APIRouter(prefix="/taxonomy", tags=["taxonomy"])


def _skill_hit(skill: Skill) -> SkillHit:
    return SkillHit(
        id=skill.id,
        name=skill.name,
        synonyms=list(skill.synonyms),
        specializations=list(skill.specializations),
    )


@router.get("/skills", response_model=list[SkillHit])
async def search_skills_route(
    q: str = "",
    limit: int = 10,
    _: Principal = Depends(get_principal),
) -> list[SkillHit]:
    return [_skill_hit(skill) for skill in search_skills(q, limit)]


@router.get("/specializations", response_model=list[SpecializationOut])
async def list_specializations_route(_: Principal = Depends(get_principal)) -> list[SpecializationOut]:
    return [
        SpecializationOut(id=item.id, name=item.name, adjacent=list(item.adjacent)) for item in list_specializations()
    ]


@router.get("/domains", response_model=list[DomainOut])
async def list_domains_route(_: Principal = Depends(get_principal)) -> list[DomainOut]:
    return [DomainOut(id=item.id, name=item.name) for item in list_domains()]


@router.get("/decline-reasons", response_model=list[DeclineReasonOut])
async def list_decline_reasons_route(_: Principal = Depends(get_principal)) -> list[DeclineReasonOut]:
    return [DeclineReasonOut(id=item.id, name=item.name) for item in list_decline_reasons()]
