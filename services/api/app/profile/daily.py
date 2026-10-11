"""One short skill story a day. Answers go on the profile; a boost lasts through tomorrow."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.profile.models import Candidate, CandidateSkill, DailyTaskAnswer
from app.profile.schemas import DailyStory, DailyTaskIn, DailyTaskView

logger = logging.getLogger(__name__)

HINT = (
    "Ответ появится в профиле — его увидят работодатели. "
    "За выполнение даётся буст в подборках на весь следующий день."
)

SKILL_LABELS: dict[str, str] = {
    "redis": "Redis",
    "postgresql": "PostgreSQL",
    "kafka": "Kafka",
    "go": "Go",
    "python": "Python",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "javascript": "JavaScript",
    "react": "React",
    "vue": "Vue",
}

FALLBACK_SKILLS = tuple(SKILL_LABELS.keys())


def today(moment: date | None = None) -> date:
    return moment or datetime.now(UTC).date()


def boost_until_for(day: date) -> datetime:
    """Active today and through the whole next calendar day."""
    return datetime(day.year, day.month, day.day, tzinfo=UTC) + timedelta(days=2)


def boost_active(until: datetime | None, moment: date | None = None) -> bool:
    if until is None:
        return False
    end = until.astimezone(UTC).date() if until.tzinfo else until.date()
    return today(moment) < end


def prompt_for(label: str) -> str:
    return f"Опиши свой лучший опыт использования {label}."


def pick_skill(candidate_id: UUID, day: date, owned: list[str], used: set[str]) -> tuple[str, str]:
    pool = [skill for skill in FALLBACK_SKILLS if skill in owned] or list(FALLBACK_SKILLS)
    fresh = [skill for skill in pool if skill not in used] or pool
    fresh.sort()
    digest = sha256(f"{candidate_id}:{day.isoformat()}".encode()).digest()
    skill_id = fresh[int.from_bytes(digest[:4], "big") % len(fresh)]
    return skill_id, SKILL_LABELS[skill_id]


def story_out(row: DailyTaskAnswer) -> DailyStory:
    return DailyStory(
        id=row.id,
        day=row.day,
        skill_id=row.skill_id,
        skill_label=row.skill_label,
        prompt=row.prompt,
        answer=row.answer,
        answered_at=row.created_at,
        boost_until=row.boost_until,
    )


async def stories_for(session: AsyncSession, candidate_id: UUID, limit: int = 12) -> list[DailyStory]:
    rows = await session.scalars(
        select(DailyTaskAnswer)
        .where(DailyTaskAnswer.candidate_id == candidate_id)
        .order_by(DailyTaskAnswer.day.desc(), DailyTaskAnswer.created_at.desc())
        .limit(limit)
    )
    return [story_out(row) for row in rows]


async def latest_boost_until(session: AsyncSession, candidate_id: UUID) -> datetime | None:
    row = await session.scalar(
        select(DailyTaskAnswer.boost_until)
        .where(DailyTaskAnswer.candidate_id == candidate_id)
        .order_by(DailyTaskAnswer.boost_until.desc())
        .limit(1)
    )
    return row


async def _owned_skills(session: AsyncSession, candidate: Candidate) -> list[str]:
    found: list[str] = []
    for skill_id in list(candidate.liked_skills or []):
        key = str(skill_id).strip().lower()
        if key in SKILL_LABELS and key not in found:
            found.append(key)
    rows = await session.scalars(select(CandidateSkill.skill_id).where(CandidateSkill.candidate_id == candidate.id))
    for skill_id in rows:
        key = str(skill_id).strip().lower()
        if key in SKILL_LABELS and key not in found:
            found.append(key)
    return found


async def current_task(session: AsyncSession, candidate: Candidate, moment: date | None = None) -> DailyTaskView:
    day = today(moment)
    stories = await stories_for(session, candidate.id)
    today_row = next((item for item in stories if item.day == day), None)
    used = {item.skill_id for item in stories}
    if today_row:
        skill_id, label, prompt = today_row.skill_id, today_row.skill_label, today_row.prompt
        until = today_row.boost_until
        answer = today_row.answer
    else:
        skill_id, label = pick_skill(candidate.id, day, await _owned_skills(session, candidate), used)
        prompt = prompt_for(label)
        until = None
        answer = None
    return DailyTaskView(
        day=day,
        prompt=prompt,
        skill_id=skill_id,
        skill_label=label,
        hint=HINT,
        answered=today_row is not None,
        answer=answer,
        boost_active=boost_active(until, day),
        boost_until=until,
        stories=stories,
    )


async def answer_task(session: AsyncSession, candidate: Candidate, body: DailyTaskIn) -> DailyTaskView:
    day = today()
    existing = await session.scalar(
        select(DailyTaskAnswer).where(DailyTaskAnswer.candidate_id == candidate.id, DailyTaskAnswer.day == day)
    )
    if existing is not None:
        raise AppError("daily_answered", "Сегодняшнее задание уже выполнено", status_code=409)
    view = await current_task(session, candidate, day)
    text = body.answer.strip()
    if len(text) < 40:
        raise AppError(
            "validation_error",
            "Напишите не меньше 40 символов — это короткий рассказ, не одно слово",
            status_code=422,
        )
    now = datetime.now(UTC)
    session.add(
        DailyTaskAnswer(
            candidate_id=candidate.id,
            day=day,
            skill_id=view.skill_id,
            skill_label=view.skill_label,
            prompt=view.prompt,
            answer=text,
            boost_until=boost_until_for(day),
            created_at=now,
        )
    )
    candidate.last_active_at = now
    await session.flush()
    try:
        from app.matching.service import invalidate_candidate

        await invalidate_candidate(candidate.id)
    except Exception:
        logger.warning("daily-task cache invalidate skipped", exc_info=True)
    return await current_task(session, candidate, day)
