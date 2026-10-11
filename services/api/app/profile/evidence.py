"""Build evidence_units from projects, resume experience, and FSP achievements.

The task is registered on app.tasks.broker. The API also runs it in-process:
the worker command only imports app.tasks, so it will not see this task until
that module imports app.profile.evidence.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import db
from app.core.errors import AppError
from app.core.models import User
from app.profile.fsp import load_achievements
from app.profile.models import Candidate, EvidenceUnit, Experience, FspAchievement, Project
from app.profile.parsing import as_date, canonical_role
from app.tasks import broker
from app.taxonomy.service import normalize, normalize_domain

logger = logging.getLogger(__name__)


@dataclass
class Draft:
    origin: str
    origin_id: UUID
    task: str
    domain: str | None
    skills: list[str]
    role: str
    occurred_on: date | None
    trust: float
    evidence_span: str


def trust_for(origin: str, source: str | None = None) -> float:
    """§6.5 trust by origin. Self-written projects stay at 0.35."""
    if origin == "fsp":
        return 1.0
    if origin == "experience":
        return 0.6
    if source == "resume":
        return 0.6
    if source == "github":
        return 0.8
    if source in {"test", "fsp_id", "fsp"}:
        return 1.0
    return 0.35


def _quoted(span: object, source: str) -> str | None:
    if not isinstance(span, str):
        return None
    text = span.strip()
    if text and text in source:
        return text
    return None


def _skill_ids(*groups: list[Any]) -> list[str]:
    found: list[str] = []
    for group in groups:
        for raw in group:
            sid = normalize(str(raw))
            if sid and sid not in found:
                found.append(sid)
    return found


def _embed_text(task: str, domain: str | None, skills: list[str]) -> str:
    parts = [task.strip()]
    if domain:
        parts.append(domain)
    if skills:
        parts.append(" ".join(skills))
    return " ".join(part for part in parts if part)


def _project_text(row: Project) -> str:
    parts = [row.task, row.outcome or "", row.scale or "", ", ".join(row.skills or []), row.url or ""]
    return "\n".join(part for part in parts if part)


def _experience_text(row: Experience) -> str:
    parts = [row.company, row.role, row.description or "", row.evidence_span or ""]
    return "\n".join(part for part in parts if part)


def _fsp_text(row: FspAchievement, skill_names: list[str]) -> str:
    place = f"место {row.place}" if row.place is not None else ""
    year = str(row.year) if row.year else ""
    parts = [row.event, row.discipline, place, year, ", ".join(skill_names)]
    return "\n".join(part for part in parts if part)


async def _draft(
    source: str,
    *,
    origin: str,
    origin_id: UUID,
    fallback_task: str,
    fallback_role: str,
    fallback_date: date | None,
    extra_skills: list[str],
    trust: float,
    lock_role: bool,
) -> Draft | None:
    from app.llm.service import extract

    if not source.strip():
        return None
    extracted = await extract("evidence_unit", source)
    span = _quoted(extracted.get("evidence_span"), source)
    if span is None:
        return None
    task = str(extracted.get("task") or "").strip() or fallback_task.strip()
    if not task:
        return None
    raw_domain = extracted.get("domain")
    domain = normalize_domain(raw_domain) if isinstance(raw_domain, str) and raw_domain.strip() else None
    raw_role = extracted.get("role") if isinstance(extracted.get("role"), str) else None
    role = fallback_role if lock_role else canonical_role(raw_role, fallback_role)
    raw_date = extracted.get("date")
    occurred = fallback_date if fallback_date is not None else as_date(raw_date if isinstance(raw_date, str) else None)
    return Draft(
        origin=origin,
        origin_id=origin_id,
        task=task,
        domain=domain,
        skills=_skill_ids(list(extracted.get("skills") or []), extra_skills),
        role=role,
        occurred_on=occurred,
        trust=trust,
        evidence_span=span,
    )


def _seed_skills(row: FspAchievement, seed: list[dict[str, Any]]) -> list[str]:
    for item in seed:
        if (
            item.get("discipline") == row.discipline
            and item.get("event") == row.event
            and item.get("year") == row.year
            and item.get("place") == row.place
        ):
            return [str(skill) for skill in item.get("skills") or []]
    return []


async def rebuild(session: AsyncSession, candidate_id: UUID) -> None:
    """Replace evidence_units for one candidate. Caller commits."""
    candidate = await session.get(Candidate, candidate_id)
    projects = list(
        await session.scalars(select(Project).where(Project.candidate_id == candidate_id).order_by(Project.created_at))
    )
    experiences = list(await session.scalars(select(Experience).where(Experience.candidate_id == candidate_id)))
    achievements = list(
        await session.scalars(select(FspAchievement).where(FspAchievement.candidate_id == candidate_id))
    )
    user = await session.get(User, candidate.user_id) if candidate is not None else None
    seed = load_achievements(user.kc_sub if user else "", user.email if user else None)

    drafts: list[Draft] = []
    for project in projects:
        draft = await _draft(
            _project_text(project),
            origin="project",
            origin_id=project.id,
            fallback_task=project.task,
            fallback_role=project.role,
            fallback_date=project.occurred_on,
            extra_skills=list(project.skills or []),
            trust=trust_for("project", project.source),
            lock_role=True,
        )
        if draft is not None:
            drafts.append(draft)
    for experience in experiences:
        draft = await _draft(
            _experience_text(experience),
            origin="experience",
            origin_id=experience.id,
            fallback_task=experience.description or f"{experience.role} в {experience.company}".strip(),
            fallback_role="participant",
            fallback_date=experience.end or experience.start,
            extra_skills=[],
            trust=trust_for("experience"),
            lock_role=False,
        )
        if draft is not None:
            drafts.append(draft)
    for achievement in achievements:
        names = _seed_skills(achievement, seed)
        when = date(achievement.year, 1, 1) if achievement.year else None
        draft = await _draft(
            _fsp_text(achievement, names),
            origin="fsp",
            origin_id=achievement.id,
            fallback_task=f"{achievement.event}: {achievement.discipline}",
            fallback_role="participant",
            fallback_date=when,
            extra_skills=[*names, achievement.discipline],
            trust=trust_for("fsp"),
            lock_role=False,
        )
        if draft is not None:
            drafts.append(draft)

    from app.embeddings.service import embed

    vectors = await embed([_embed_text(item.task, item.domain, item.skills) for item in drafts], prefix="passage")
    if len(vectors) != len(drafts):
        raise AppError("embedding_failed", "Не удалось посчитать эмбеддинги единиц опыта", status_code=500)
    await session.execute(delete(EvidenceUnit).where(EvidenceUnit.candidate_id == candidate_id))
    for draft, vector in zip(drafts, vectors, strict=True):
        session.add(
            EvidenceUnit(
                candidate_id=candidate_id,
                origin=draft.origin,
                origin_id=draft.origin_id,
                task=draft.task,
                domain=draft.domain,
                skills=draft.skills,
                role=draft.role,
                occurred_on=draft.occurred_on,
                trust=draft.trust,
                evidence_span=draft.evidence_span,
                embedding=vector,
            )
        )
    await session.flush()


async def recompute(candidate_id: UUID) -> None:
    try:
        from app.hints.service import recompute_candidate

        await recompute_candidate(candidate_id)
    except Exception:
        logger.exception("recompute_candidate failed for %s", candidate_id)


async def run(candidate_id: UUID) -> None:
    async with db.SessionLocal() as session:
        await rebuild(session, candidate_id)
        await session.commit()
    await recompute(candidate_id)


async def kick(candidate_id: UUID) -> None:
    try:
        await asyncio.wait_for(rebuild_evidence.kiq(str(candidate_id)), timeout=0.25)
    except Exception:
        logger.info("rebuild_evidence was not queued for %s", candidate_id)


@broker.task
async def rebuild_evidence(candidate_id: str) -> None:
    await run(UUID(candidate_id))
