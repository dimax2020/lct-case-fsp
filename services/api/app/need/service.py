"""Persist needs, parse requirements, and start a shortlist job."""

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

import app.matching.service as matching
import app.profile.service as profile_api
from app.core.auth import Principal
from app.core.db import SessionLocal
from app.core.enums import Grade, RequirementKind, Specialization, WorkFormat, grade_distance
from app.core.errors import AppError
from app.core.jobs import create_job, set_job_status
from app.core.provision import provision_user
from app.core.settings import get_settings
from app.embeddings.service import embed
from app.llm.service import extract
from app.matching.service import ShortlistQuery
from app.need.models import Need, NeedRequirement
from app.need.schemas import (
    CandidateCard,
    CategorySuggestion,
    NeedOut,
    NeedWrite,
    ParseResult,
    RequirementOut,
    ShortlistOut,
)

logger = logging.getLogger(__name__)

MAX_REQUIREMENTS = 40


@dataclass
class ParsePlan:
    requirements: list[dict[str, object]]
    category: CategorySuggestion | None
    llm_used: bool
    embeddings: list[list[float]] | None


def _as_skills(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def embed_text(task: str, domain: str | None, skills: list[str]) -> str:
    parts = [task.strip()]
    if domain and domain.strip():
        parts.append(domain.strip())
    if skills:
        parts.append(" ".join(skills))
    return " ".join(part for part in parts if part)


def requirements_from_form(must_skills: list[str], nice_skills: list[str], domain: str | None) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for skill in must_skills:
        rows.append(
            {
                "task": skill,
                "domain": domain,
                "skills": [skill],
                "scale": None,
                "kind": RequirementKind.must.value,
                "evidence_span": None,
            }
        )
    for skill in nice_skills:
        rows.append(
            {
                "task": skill,
                "domain": domain,
                "skills": [skill],
                "scale": None,
                "kind": RequirementKind.nice.value,
                "evidence_span": None,
            }
        )
    return rows


def _category_from_raw(raw: dict[str, object]) -> CategorySuggestion | None:
    try:
        specialization = Specialization(str(raw.get("specialization")))
        grades_raw = raw.get("grades") or []
        if not isinstance(grades_raw, list):
            return None
        grades = [str(item) for item in grades_raw]
        if not grades or len(grades) > 2:
            return None
        for grade in grades:
            Grade(grade)
        if len(grades) == 2 and grade_distance(grades[0], grades[1]) != 1:
            return None
    except (ValueError, KeyError):
        return None
    domain = raw.get("domain")
    span = raw.get("evidence_span")
    return CategorySuggestion(
        specialization=specialization,
        grades=grades,
        domain=None if domain is None else str(domain),
        evidence_span=None if span is None else str(span),
    )


def _requirements_from_raw(raw: dict[str, object], description: str) -> list[dict[str, object]]:
    items = raw.get("requirements")
    if not isinstance(items, list):
        return []
    rows: list[dict[str, object]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        task = str(item.get("task") or "").strip()
        span = str(item.get("evidence_span") or "").strip()
        kind = str(item.get("kind") or "")
        known_kinds = {RequirementKind.must.value, RequirementKind.nice.value}
        if not task or not span or span not in description or kind not in known_kinds:
            continue
        skills_raw = item.get("skills") or []
        skills = [str(skill) for skill in skills_raw] if isinstance(skills_raw, list) else []
        domain = item.get("domain")
        scale = item.get("scale")
        rows.append(
            {
                "task": task,
                "domain": None if domain is None else str(domain),
                "skills": skills,
                "scale": None if scale is None else str(scale),
                "kind": kind,
                "evidence_span": span,
            }
        )
        if len(rows) >= MAX_REQUIREMENTS:
            break
    return rows


async def plan_parse(
    description: str,
    must_skills: list[str],
    nice_skills: list[str],
    domain: str | None,
) -> ParsePlan:
    if not get_settings().llm_enabled:
        return ParsePlan(
            requirements=requirements_from_form(must_skills, nice_skills, domain),
            category=None,
            llm_used=False,
            embeddings=None,
        )
    extracted = await extract("need_requirements", description)
    category_raw = await extract("need_category", description)
    requirements = _requirements_from_raw(extracted if isinstance(extracted, dict) else {}, description)
    embeddings: list[list[float]] | None = None
    if requirements:
        texts = [
            embed_text(
                str(item["task"]),
                None if item["domain"] is None else str(item["domain"]),
                _as_skills(item["skills"]),
            )
            for item in requirements
        ]
        vectors = await embed(texts)
        embeddings = [list(vector) for vector in vectors]
    category = _category_from_raw(category_raw) if isinstance(category_raw, dict) else None
    return ParsePlan(requirements=requirements, category=category, llm_used=True, embeddings=embeddings)


def to_out(need: Need) -> NeedOut:
    return NeedOut(
        id=need.id,
        title=need.title,
        specialization=Specialization(need.specialization),
        grades=list(need.grades),
        salary_from=need.salary_from,
        salary_to=need.salary_to,
        formats=[WorkFormat(item) for item in need.formats],
        city=need.city,
        must_skills=list(need.must_skills),
        nice_skills=list(need.nice_skills or []),
        description=need.description,
        domain=need.domain or "",
        stages=need.stages,
        status=need.status,
        company_id=need.company_id,
    )


async def employer_company_id(session: AsyncSession, principal: Principal) -> UUID:
    user = await provision_user(session, principal)
    found = await session.execute(
        text("SELECT id FROM companies WHERE owner_user_id = :uid"),
        {"uid": user.id},
    )
    company_id = found.scalar_one_or_none()
    if company_id is not None:
        return company_id
    inserted = await session.execute(
        text(
            """
            INSERT INTO companies (id, owner_user_id, name, recruiter_contact, benefits)
            VALUES (:id, :uid, '', CAST('{}' AS jsonb), '{}')
            ON CONFLICT (owner_user_id) DO UPDATE SET name = companies.name
            RETURNING id
            """
        ),
        {"id": uuid4(), "uid": user.id},
    )
    return inserted.scalar_one()


async def require_need(session: AsyncSession, principal: Principal, need_id: UUID) -> Need:
    company_id = await employer_company_id(session, principal)
    need = await session.get(Need, need_id)
    if need is None or need.company_id != company_id:
        raise AppError("not_found", "Потребность не найдена", status_code=404)
    return need


async def list_needs(session: AsyncSession, principal: Principal) -> list[NeedOut]:
    company_id = await employer_company_id(session, principal)
    result = await session.execute(select(Need).where(Need.company_id == company_id).order_by(Need.created_at.desc()))
    return [to_out(need) for need in result.scalars()]


async def create_need(session: AsyncSession, principal: Principal, body: NeedWrite) -> NeedOut:
    company_id = await employer_company_id(session, principal)
    need = Need(
        company_id=company_id,
        title=body.title,
        specialization=body.specialization.value,
        grades=list(body.grades),
        salary_from=body.salary_from,
        salary_to=body.salary_to,
        formats=[item.value for item in body.formats],
        city=body.city,
        must_skills=list(body.must_skills),
        nice_skills=list(body.nice_skills),
        description=body.description,
        domain=body.domain,
        stages=body.stages,
        status="open",
    )
    session.add(need)
    await session.flush()
    return to_out(need)


async def get_need(session: AsyncSession, principal: Principal, need_id: UUID) -> NeedOut:
    return to_out(await require_need(session, principal, need_id))


async def update_need(session: AsyncSession, principal: Principal, need_id: UUID, body: NeedWrite) -> NeedOut:
    need = await require_need(session, principal, need_id)
    description_changed = need.description != body.description
    need.title = body.title
    need.specialization = body.specialization.value
    need.grades = list(body.grades)
    need.salary_from = body.salary_from
    need.salary_to = body.salary_to
    need.formats = [item.value for item in body.formats]
    need.city = body.city
    need.must_skills = list(body.must_skills)
    need.nice_skills = list(body.nice_skills)
    need.description = body.description
    need.domain = body.domain
    need.stages = body.stages
    if description_changed:
        await session.execute(delete(NeedRequirement).where(NeedRequirement.need_id == need.id))
    await session.flush()
    await matching.invalidate(need.id)
    return to_out(need)


def _usable_vector(vector: list[float] | None) -> list[float] | None:
    if not vector or not any(component != 0.0 for component in vector):
        return None
    return vector


async def parse_need(session: AsyncSession, principal: Principal, need_id: UUID) -> ParseResult:
    need = await require_need(session, principal, need_id)
    plan = await plan_parse(need.description, list(need.must_skills), list(need.nice_skills or []), need.domain)
    await session.execute(delete(NeedRequirement).where(NeedRequirement.need_id == need.id))
    stored: list[NeedRequirement] = []
    for index, item in enumerate(plan.requirements):
        vector = None
        if plan.embeddings is not None and index < len(plan.embeddings):
            vector = _usable_vector(plan.embeddings[index])
        skills = item["skills"]
        row = NeedRequirement(
            need_id=need.id,
            task=str(item["task"]),
            domain=None if item["domain"] is None else str(item["domain"]),
            skills=list(skills) if isinstance(skills, list) else [],
            scale=None if item["scale"] is None else str(item["scale"]),
            kind=str(item["kind"]),
            evidence_span=None if item["evidence_span"] is None else str(item["evidence_span"]),
            embedding=vector,
        )
        session.add(row)
        stored.append(row)
    await session.flush()
    await matching.invalidate(need.id)
    return ParseResult(
        category=plan.category,
        requirements=[
            RequirementOut(
                id=row.id,
                task=row.task,
                domain=row.domain,
                skills=list(row.skills or []),
                scale=row.scale,
                kind=RequirementKind(row.kind),
                evidence_span=row.evidence_span,
            )
            for row in stored
        ],
        llm_used=plan.llm_used,
    )


async def open_match_job(session: AsyncSession, principal: Principal, need_id: UUID) -> UUID:
    need = await require_need(session, principal, need_id)
    job = await create_job(session, "need.match", {"need_id": str(need.id)})
    await session.flush()
    return job.id


async def enqueue_match(need_id: UUID, job_id: UUID) -> None:
    from app.need.tasks import match_need_task

    try:
        await match_need_task.kiq(str(need_id), str(job_id))
    except Exception as exc:
        logger.warning("match job was not queued", exc_info=True)
        async with SessionLocal() as session:
            await set_job_status(session, job_id, "failed", error=f"{type(exc).__name__}: {exc}"[:2000])
            await session.commit()


async def execute_match(need_id: str, job_id: str) -> None:
    from app.hints.service import recompute_employer

    parsed_need = UUID(need_id)
    parsed_job = UUID(job_id)
    async with SessionLocal() as session:
        await set_job_status(session, parsed_job, "running")
        await session.commit()
    try:
        shortlist = await matching.build_shortlist_strict(parsed_need)
        try:
            await recompute_employer(parsed_need)
        except Exception:
            logger.exception("employer hints were not warmed")
        async with SessionLocal() as session:
            await set_job_status(
                session,
                parsed_job,
                "done",
                result={"need_id": need_id, "count": len(shortlist.items), "hidden": len(shortlist.hidden)},
            )
            await session.commit()
    except Exception as exc:
        async with SessionLocal() as session:
            await set_job_status(session, parsed_job, "failed", error=f"{type(exc).__name__}: {exc}"[:2000])
            await session.commit()
        raise


async def get_shortlist(session: AsyncSession, principal: Principal, need_id: UUID, query: ShortlistQuery) -> ShortlistOut:
    need = await require_need(session, principal, need_id)
    payload = await matching.present_shortlist(need_id, query)
    if payload is None:
        raise AppError("not_found", "Потребность не найдена", status_code=404)
    payload = await apply_privacy(session, need.company_id, payload)
    return ShortlistOut.model_validate(payload)


def _privacy_rules(row: dict[str, Any], rules: dict[str, Any] | None, company_id: UUID) -> dict[str, Any] | None:
    """Применяет настройки приватности кандидата к строке выдачи. None — строку показывать нельзя."""
    if rules is None:
        return row
    hidden = rules.get("hidden_company_ids") or set()
    if not rules.get("visible", True) or company_id in hidden:
        return None
    row["display_name"] = rules.get("name") or row.get("display_name")
    if not rules.get("show_fsp", True):
        row["fsp_badge"] = None
    return row


async def apply_privacy(session: AsyncSession, company_id: UUID, payload: dict[str, Any]) -> dict[str, Any]:
    items: list[dict[str, Any]] = list(payload.get("items") or [])
    ids: list[UUID] = []
    for item in items:
        try:
            ids.append(UUID(str(item.get("candidate_id"))))
        except (TypeError, ValueError):
            continue
    privacy = await profile_api.privacy_for(session, ids)
    kept: list[dict[str, Any]] = []
    for item in items:
        try:
            key = UUID(str(item.get("candidate_id")))
        except (TypeError, ValueError):
            continue
        shown = _privacy_rules(item, privacy.get(key), company_id)
        if shown is not None:
            kept.append(shown)
    removed = len(items) - len(kept)
    first = int(items[0].get("position") or 1) if items else 1
    for position, item in enumerate(kept, start=first):
        item["position"] = position
    payload["items"] = kept
    payload["total"] = max(0, int(payload.get("total") or 0) - removed)
    return payload


async def resolve_contacts(
    session: AsyncSession,
    need_id: UUID,
    candidate_id: UUID,
) -> tuple[bool, str | None, str | None]:
    """Contacts come from the invitation card and stay hidden until accepted."""
    import app.invitation.service as invitation_service

    card = await invitation_service.build_candidate_card(session, need_id, candidate_id)
    return bool(card.get("contacts_revealed")), card.get("email"), card.get("phone")


async def _invitation_status(session: AsyncSession, need_id: UUID, candidate_id: UUID) -> str | None:
    row = (
        await session.execute(
            text("SELECT status FROM invitations WHERE need_id = :need_id AND candidate_id = :candidate_id"),
            {"need_id": need_id, "candidate_id": candidate_id},
        )
    ).first()
    return str(row[0]) if row is not None else None


async def get_candidate_card(
    session: AsyncSession,
    principal: Principal,
    need_id: UUID,
    candidate_id: UUID,
) -> CandidateCard:
    need = await require_need(session, principal, need_id)
    privacy = (await profile_api.privacy_for(session, [candidate_id])).get(candidate_id)
    if privacy is not None and (not privacy["visible"] or need.company_id in privacy["hidden_company_ids"]):
        raise AppError("not_found", "Кандидат не найден", status_code=404)
    card = await matching.candidate_card(need_id, candidate_id)
    in_shortlist = card is not None
    if card is None:
        # Кандидат найден через банк, но в подборку этой потребности не попал.
        card = await profile_api.basic_card(session, candidate_id)
        if card is None:
            raise AppError("not_found", "Кандидат не найден", status_code=404)
        card["invitation_status"] = await _invitation_status(session, need_id, candidate_id)
    revealed, email, phone = await resolve_contacts(session, need_id, candidate_id)
    card["contacts_revealed"] = revealed
    card["email"] = email if revealed else None
    card["phone"] = phone if revealed else None
    card["in_shortlist"] = in_shortlist
    if privacy is not None:
        card["display_name"] = privacy["name"] or card.get("display_name")
        if not privacy["show_fsp"]:
            card["fsp_badge"] = None
        card["current_job"] = privacy["current_job"]
        card["pdf_available"] = bool(privacy["show_pdf"])
        card["psych_available"] = bool(privacy["show_psych"])
    card["daily_stories"] = await profile_api.list_daily_stories(session, candidate_id)
    return CandidateCard.model_validate(card)


async def candidate_pdf(session: AsyncSession, principal: Principal, need_id: UUID, candidate_id: UUID) -> bytes:
    """PDF-профиль кандидата для работодателя: контакты — только после принятия приглашения."""
    need = await require_need(session, principal, need_id)
    privacy = (await profile_api.privacy_for(session, [candidate_id])).get(candidate_id)
    if privacy is None or not privacy["visible"] or need.company_id in privacy["hidden_company_ids"]:
        raise AppError("not_found", "Кандидат не найден", status_code=404)
    revealed, _, _ = await resolve_contacts(session, need_id, candidate_id)
    payload = await profile_api.employer_profile_pdf(session, candidate_id, revealed)
    if payload is None:
        raise AppError("forbidden", "Кандидат не открыл PDF-профиль работодателям", status_code=403)
    return payload
