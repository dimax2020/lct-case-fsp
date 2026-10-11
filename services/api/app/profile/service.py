"""Public profile API. Other modules import only this file.

ORM details live in app.profile.storage, which the profile router imports.
That keeps this module free of profile.models so neighbours can depend on it.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import db
from app.core.auth import Principal


@dataclass
class SkillFeature:
    skill_id: str
    score: float | None
    source: str


@dataclass
class EvidenceFeature:
    id: str
    task: str
    domain: str | None
    skills: list[str]
    role: str
    date: date | None
    trust: float
    embedding: list[float] | None
    origin: str
    evidence_span: str | None = None


@dataclass
class FspFeature:
    discipline: str
    event: str
    place: int | None
    year: int | None


@dataclass
class CandidateFeatures:
    candidate_id: str
    full_name: str
    display_name: str
    specialization: str | None
    grade: str | None
    grade_score: float | None
    min_salary: int | None
    formats: list[str]
    status: str
    visible: bool
    city: str | None
    liked_skills: list[str]
    disliked_skills: list[str]
    liked_domains: list[str]
    blocked_domains: list[str]
    last_active_at: datetime | None
    skills: list[SkillFeature] = field(default_factory=list)
    evidence: list[EvidenceFeature] = field(default_factory=list)
    fsp: list[FspFeature] = field(default_factory=list)
    open_invites: int = 0
    experience_years: float | None = None


_storage: Any = None


def bind(storage: Any) -> None:
    global _storage
    _storage = storage


def _api() -> Any:
    if _storage is None:
        raise RuntimeError("profile storage is not configured")
    return _storage


async def get_db() -> AsyncIterator[AsyncSession]:
    async with db.SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_candidate_features(candidate_id: UUID) -> CandidateFeatures:
    """Read matching features from the database. A missing row is an empty profile."""
    return await _api().get_candidate_features(candidate_id)


async def ensure_candidate(user_id: UUID) -> UUID:
    """Create the candidate row for a user and return its id."""
    return await _api().ensure_candidate(user_id)


async def current_candidate(session: AsyncSession, principal: Principal) -> Any:
    return await _api().current_candidate(session, principal)


async def apply_confirmed_resume(
    session: AsyncSession,
    candidate_id: UUID,
    payload: dict[str, Any],
    raw_text: str,
) -> dict[str, Any]:
    """Store resume rows that have a quote in the source text, then rebuild evidence."""
    return await _api().apply_confirmed_resume(session, candidate_id, payload, raw_text)


async def finish_evidence(session: AsyncSession, candidate_id: UUID) -> None:
    await _api().finish_evidence(session, candidate_id)
