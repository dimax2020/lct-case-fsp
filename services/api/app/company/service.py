"""Company profile. The first employer login creates an empty company."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.company.models import Company
from app.company.schemas import CompanyBrief, CompanyOut, CompanyWrite, RecruiterContact
from app.core.auth import Principal
from app.core.enums import Benefit
from app.core.errors import AppError
from app.core.models import User
from app.core.provision import provision_user, set_company_hook


@dataclass(frozen=True)
class CompanyProfile:
    id: UUID
    owner_user_id: UUID
    name: str
    city: str | None
    size: str | None
    industry: str | None
    about: str | None
    recruiter_contact: dict[str, Any]
    benefits: list[str]


def format_recruiter_contact(contact: Mapping[str, Any] | None) -> str | None:
    if not contact:
        return None
    parts: list[str] = []
    for key in ("name", "email", "phone"):
        value = contact.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    return ", ".join(parts) or None


def _parse_benefits(values: list[str] | None) -> list[Benefit]:
    parsed: list[Benefit] = []
    for item in values or []:
        try:
            benefit = Benefit(item)
        except ValueError:
            continue
        if benefit not in parsed:
            parsed.append(benefit)
    return parsed


def _to_profile(company: Company) -> CompanyProfile:
    return CompanyProfile(
        id=company.id,
        owner_user_id=company.owner_user_id,
        name=company.name or "",
        city=company.city,
        size=company.size,
        industry=company.industry,
        about=company.about,
        recruiter_contact=dict(company.recruiter_contact or {}),
        benefits=list(company.benefits or []),
    )


def to_out(company: Company) -> CompanyOut:
    return CompanyOut(
        id=company.id,
        name=company.name or "",
        city=company.city,
        size=company.size,
        industry=company.industry,
        about=company.about,
        recruiter_contact=RecruiterContact.model_validate(company.recruiter_contact or {}),
        benefits=_parse_benefits(list(company.benefits or [])),
        website=company.website,
        logo=company.logo,
    )


async def search_companies(session: AsyncSession, query: str, limit: int = 10) -> list[CompanyBrief]:
    text = query.strip()
    if len(text) < 2:
        return []
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    rows = await session.scalars(
        select(Company)
        .where(Company.name != "", Company.name.ilike(f"%{escaped}%", escape="\\"))
        .order_by(Company.name)
        .limit(max(1, min(limit, 20)))
    )
    return [CompanyBrief(id=row.id, name=row.name, city=row.city) for row in rows]


async def ensure_company_for_user(session: AsyncSession, user: User) -> None:
    found = await session.scalar(select(Company.id).where(Company.owner_user_id == user.id))
    if found is not None:
        return
    session.add(Company(owner_user_id=user.id, name="", recruiter_contact={}, benefits=[]))
    await session.flush()


def register_company_hook() -> None:
    set_company_hook(ensure_company_for_user)


async def current_user(session: AsyncSession, principal: Principal) -> User:
    user = await provision_user(session, principal)
    await session.commit()
    return user


async def _require_company(session: AsyncSession, user: User) -> Company:
    await ensure_company_for_user(session, user)
    await session.commit()
    company = await session.scalar(select(Company).where(Company.owner_user_id == user.id))
    if company is None:
        raise AppError("not_found", "Компания не найдена", status_code=404)
    return company


async def get_my_company(session: AsyncSession, principal: Principal) -> CompanyOut:
    user = await current_user(session, principal)
    return to_out(await _require_company(session, user))


async def update_my_company(session: AsyncSession, principal: Principal, body: CompanyWrite) -> CompanyOut:
    user = await current_user(session, principal)
    company = await _require_company(session, user)
    company.name = body.name
    company.city = body.city
    company.size = body.size
    company.industry = body.industry
    company.about = body.about
    company.website = body.website
    company.logo = body.logo
    company.recruiter_contact = body.recruiter_contact.model_dump(exclude_none=True)
    benefits: list[str] = []
    for item in body.benefits:
        if item.value not in benefits:
            benefits.append(item.value)
    company.benefits = benefits
    await session.commit()
    await session.refresh(company)
    return to_out(company)


async def get_profile(session: AsyncSession, company_id: UUID) -> CompanyProfile | None:
    company = await session.get(Company, company_id)
    if company is None:
        return None
    return _to_profile(company)


async def get_owned_profile(session: AsyncSession, owner_user_id: UUID) -> CompanyProfile | None:
    company = await session.scalar(select(Company).where(Company.owner_user_id == owner_user_id))
    if company is None:
        return None
    return _to_profile(company)


register_company_hook()
