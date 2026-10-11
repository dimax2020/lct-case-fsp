"""Shortlist seam. Agent D replaces the bodies; signatures stay."""

from dataclasses import dataclass, field
from uuid import UUID

from app.profile.service import CandidateFeatures


@dataclass
class RequirementView:
    id: str
    task: str
    domain: str | None
    skills: list[str]
    scale: str | None
    kind: str
    embedding: list[float] | None = None


@dataclass
class NeedView:
    id: str
    specialization: str
    grades: list[str]
    salary_from: int
    salary_to: int
    formats: list[str]
    city: str | None
    must_skills: list[str]
    nice_skills: list[str]
    domain: str | None
    stages: int
    benefits: list[str] = field(default_factory=list)
    requirements: list[RequirementView] = field(default_factory=list)
    description: str = ""


@dataclass
class PairExplanation:
    requirement_id: str
    evidence_id: str
    text: str
    score: float


@dataclass
class ScoreBreakdown:
    s: float
    e: float
    c: float
    features: dict[str, float]
    explanations: list[str]
    gated: bool
    best_pairs: list[PairExplanation] = field(default_factory=list)


@dataclass
class ShortlistItem:
    candidate_id: str
    position: int
    score: float
    breakdown: ScoreBreakdown
    hidden_by_filter: bool


@dataclass
class CategoryTile:
    id: str
    title: str
    count: int


@dataclass
class Shortlist:
    need_id: str
    items: list[ShortlistItem]
    hidden: list[ShortlistItem]
    categories: list[CategoryTile]


def _stub_breakdown() -> ScoreBreakdown:
    return ScoreBreakdown(
        s=0.5,
        e=0.5,
        c=1.0,
        features={
            "must_cov": 0.5,
            "grade_fit": 1.0,
            "ef": 0.0,
            "skill_avg": 0.0,
            "fsp": 0.0,
            "fresh": 1.0,
            "nice_cov": 0.0,
        },
        explanations=["Заглушка фазы 0"],
        gated=False,
        best_pairs=[],
    )


async def score_pair(need: NeedView, candidate: CandidateFeatures) -> ScoreBreakdown:
    del need, candidate
    return _stub_breakdown()


async def build_shortlist(need_id: UUID) -> Shortlist:
    return Shortlist(need_id=str(need_id), items=[], hidden=[], categories=[])


async def invalidate(need_id: UUID) -> None:
    del need_id
