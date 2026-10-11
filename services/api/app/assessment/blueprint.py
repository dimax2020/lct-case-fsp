"""Vacancy → CAT blueprint: shift topic quotas toward need skills."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment.item_bank import PLATFORM_TO_BANK, items_for, vacancies
from app.assessment.schemas import BlueprintOut, BlueprintSample
from app.core.errors import AppError


def _need_tokens(skills: list[str], description: str) -> set[str]:
    tokens = {item.lower() for item in skills}
    for word in description.lower().replace(",", " ").replace(".", " ").split():
        if len(word) >= 3:
            tokens.add(word)
    return tokens


def _score(tags: tuple[str, ...], tokens: set[str]) -> float:
    if not tags:
        return 0.0
    hit = 0.0
    for tag in tags:
        low = tag.lower()
        if low in tokens or any(part in tokens for part in low.split(".")):
            hit += 1.0
        elif any(token in low for token in tokens if len(token) >= 4):
            hit += 0.4
    return hit


def build_blueprint(specialization: str, grade: str | None, skills: list[str], description: str) -> BlueprintOut:
    items = items_for(specialization)
    tokens = _need_tokens(skills, description)
    ranked = sorted(items, key=lambda item: (-_score(item.tags, tokens), item.b))
    sample = [
        BlueprintSample(id=item.id, title=item.title, format=item.format, tags=list(item.tags))
        for item in ranked[:8]
        if _score(item.tags, tokens) > 0 or item.source == "detailed"
    ][:6]
    if not sample:
        sample = [BlueprintSample(id=item.id, title=item.title, format=item.format, tags=list(item.tags)) for item in items[:6]]
    theory = 30
    practice = 40
    debug = 20
    case = 10
    if any(item.format == "CASE" and _score(item.tags, tokens) > 0 for item in ranked[:12]):
        case = 20
        theory = 20
    bank = PLATFORM_TO_BANK.get(specialization, specialization)
    note = None
    for vacancy in vacancies():
        if str(vacancy.get("title") or "").lower().find(bank.lower()) >= 0 or str(vacancy.get("id")):
            skill_rows = vacancy.get("skills")
            vac_skills: list[str] = []
            if isinstance(skill_rows, list):
                vac_skills = [str(row.get("tag")) for row in skill_rows if isinstance(row, dict)]
            if tokens & {item.lower() for item in vac_skills}:
                note = str(vacancy.get("blueprint") or "")
                sample_raw = vacancy.get("sample")
                sample_lines = [str(line) for line in sample_raw] if isinstance(sample_raw, list) else []
                if sample_lines and not any(_score(item.tags, tokens) > 0 for item in ranked[:4]):
                    note = f"{note} Примеры: {'; '.join(sample_lines[:4])}."
                break
    return BlueprintOut(
        specialization=specialization,
        grade=grade,
        theory=theory,
        practice=practice,
        debug=debug,
        case=case,
        skills=skills,
        sample=sample,
        note=note or "Квоты смещены к тегам потребности. Грейд кандидата чертёж не меняет.",
    )


async def blueprint_for_need(session: AsyncSession, principal_company_id: UUID | None, need_id: UUID) -> BlueprintOut:
    row = (
        await session.execute(
            text(
                """
                SELECT n.specialization, n.grades, n.must_skills, n.nice_skills, n.description, n.company_id
                FROM needs n
                WHERE n.id = CAST(:id AS uuid)
                """
            ),
            {"id": str(need_id)},
        )
    ).one_or_none()
    if row is None:
        raise AppError("need_not_found", "Потребность не найдена", status_code=404)
    if principal_company_id is not None and str(row.company_id) != str(principal_company_id):
        raise AppError("need_not_found", "Потребность не найдена", status_code=404)
    grades = list(row.grades or [])
    skills = list(row.must_skills or []) + list(row.nice_skills or [])
    return build_blueprint(
        str(row.specialization),
        str(grades[0]) if grades else None,
        [str(item) for item in skills],
        str(row.description or ""),
    )
