"""Employer candidate bank. Filters and the 50-row cap are SQL, not Python."""

from typing import Any

from sqlalchemy import Select, distinct, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.profile.models import Candidate, CandidateSkill, FspAchievement
from app.profile.parsing import display_name
from app.profile.schemas import CandidateBankItem

BANK_LIMIT = 50


def blank(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def like_pattern(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def stack_tokens(stack: str | None) -> list[str]:
    text = blank(stack)
    if text is None:
        return []
    found: list[str] = []
    for part in text.replace(",", " ").split():
        token = part.strip().lower()
        if token and token not in found:
            found.append(token)
    return found


def bank_statement(
    *,
    specialization: str | None = None,
    grade: str | None = None,
    stack: str | None = None,
    fsp: bool | None = None,
    q: str | None = None,
) -> Select[Any]:
    """Visible candidates only. The select list has no phone, email, or contact_email."""
    skills = (
        select(func.array_agg(distinct(CandidateSkill.skill_id)))
        .where(CandidateSkill.candidate_id == Candidate.id)
        .scalar_subquery()
    )
    fsp_count = (
        select(func.count(FspAchievement.id))
        .where(FspAchievement.candidate_id == Candidate.id)
        .scalar_subquery()
    )
    statement = select(
        Candidate.id,
        Candidate.full_name,
        Candidate.specialization,
        Candidate.grade,
        Candidate.city,
        Candidate.grade_score.label("test_score"),
        skills.label("skills"),
        fsp_count.label("fsp_count"),
    ).where(Candidate.visible.is_(True))
    specialization_value = blank(specialization)
    if specialization_value:
        statement = statement.where(func.lower(Candidate.specialization) == specialization_value.lower())
    grade_value = blank(grade)
    if grade_value:
        statement = statement.where(func.lower(Candidate.grade) == grade_value.lower())
    for token in stack_tokens(stack):
        statement = statement.where(
            exists(
                select(CandidateSkill.id).where(
                    CandidateSkill.candidate_id == Candidate.id,
                    func.lower(CandidateSkill.skill_id) == token,
                )
            )
        )
    achievements = exists(select(FspAchievement.id).where(FspAchievement.candidate_id == Candidate.id))
    if fsp is True:
        statement = statement.where(achievements)
    elif fsp is False:
        statement = statement.where(~achievements)
    query = blank(q)
    if query:
        pattern = like_pattern(query)
        skill_hit = exists(
            select(CandidateSkill.id).where(
                CandidateSkill.candidate_id == Candidate.id,
                CandidateSkill.skill_id.ilike(pattern, escape="\\"),
            )
        )
        statement = statement.where(
            or_(
                Candidate.full_name.ilike(pattern, escape="\\"),
                Candidate.city.ilike(pattern, escape="\\"),
                Candidate.specialization.ilike(pattern, escape="\\"),
                func.coalesce(func.array_to_string(Candidate.soft_skills, " "), "").ilike(pattern, escape="\\"),
                skill_hit,
            )
        )
    return statement.order_by(Candidate.updated_at.desc().nulls_last(), Candidate.id).limit(BANK_LIMIT)


def bank_item(row: Any) -> CandidateBankItem:
    skills: list[str] = []
    for item in row.skills or []:
        text = str(item)
        if text and text not in skills:
            skills.append(text)
    score = row.test_score
    return CandidateBankItem(
        id=row.id,
        display_name=display_name(row.full_name or ""),
        specialization=row.specialization,
        grade=row.grade,
        city=row.city,
        skills=skills,
        has_fsp=int(row.fsp_count or 0) > 0,
        test_score=None if score is None else float(score),
    )


async def search_candidates(
    session: AsyncSession,
    *,
    specialization: str | None = None,
    grade: str | None = None,
    stack: str | None = None,
    fsp: bool | None = None,
    q: str | None = None,
) -> list[CandidateBankItem]:
    result = await session.execute(
        bank_statement(specialization=specialization, grade=grade, stack=stack, fsp=fsp, q=q)
    )
    return [bank_item(row) for row in result.all()]
