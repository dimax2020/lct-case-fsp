"""Public profile API. Other modules import only this file."""

from dataclasses import dataclass, field
from datetime import date, datetime
from uuid import UUID


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


def _stub_features(candidate_id: UUID) -> CandidateFeatures:
    return CandidateFeatures(
        candidate_id=str(candidate_id),
        full_name="Алексей Кузнецов",
        display_name="Алексей К.",
        specialization="backend",
        grade="middle",
        grade_score=82,
        min_salary=250_000,
        formats=["remote"],
        status="seeking",
        visible=True,
        city="Новосибирск",
        liked_skills=["go", "postgresql"],
        disliked_skills=[],
        liked_domains=["fintech"],
        blocked_domains=[],
        last_active_at=None,
        skills=[SkillFeature(skill_id="go", score=82, source="test")],
        evidence=[],
        fsp=[],
        open_invites=0,
        experience_years=4,
    )


async def get_candidate_features(candidate_id: UUID) -> CandidateFeatures:
    """Phase-0 stub with a fixed shape. Agent B reads the database."""
    return _stub_features(candidate_id)


async def ensure_candidate(user_id: UUID) -> UUID:
    """Hook target for first login. Agent B creates the candidate row."""
    return user_id
