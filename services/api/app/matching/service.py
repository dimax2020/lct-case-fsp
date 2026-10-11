"""Public matching API.

Other modules import this file only. Weights live in ``matching.config`` and are
loaded with the engine at call time: import-linter forbids a static chain from
``need`` or ``hints`` to ``matching.config``, including through this module.
"""

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.exc import InterfaceError, OperationalError

from app.profile.service import CandidateFeatures

logger = logging.getLogger(__name__)

_CONNECTION_ERRORS = (OperationalError, InterfaceError, OSError, ConnectionError, TimeoutError)


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
    coverages: dict[str, float] = field(default_factory=dict)


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


@dataclass(frozen=True)
class ShortlistQuery:
    category: str | None = None
    only_fsp: bool = False
    fsp_discipline: str | None = None
    min_test_score: int | None = None
    stack: str | None = None
    work_format: str | None = None
    active_30d: bool = False
    tab: str = "pool"
    hint_id: str | None = None
    page: int = 1
    page_size: int = 20


def _load(module: str) -> Any:
    import importlib

    return importlib.import_module(module)


def _formulas() -> Any:
    return _load("app.matching.formulas")


def _engine() -> Any:
    return _load("app.matching.engine")


def _hints() -> Any:
    return _load("app.matching.hints_algo")


def _project() -> Any:
    return _load("app.matching.project")


def _cache() -> Any:
    return _load("app.matching.cache")


def empty_shortlist(need_id: UUID | str) -> Shortlist:
    return Shortlist(need_id=str(need_id), items=[], hidden=[], categories=[])


async def score_pair(need: NeedView, candidate: CandidateFeatures) -> ScoreBreakdown:
    return _formulas().score_breakdown(need, candidate)


async def build_shortlist(need_id: UUID) -> Shortlist:
    """Return an empty shortlist when Postgres is unreachable so callers without a DB stay up."""
    try:
        return await build_shortlist_strict(need_id)
    except _CONNECTION_ERRORS:
        logger.warning("shortlist store is unreachable", exc_info=True)
        return empty_shortlist(need_id)


async def build_shortlist_strict(need_id: UUID) -> Shortlist:
    return await _engine().build_shortlist(need_id)


async def invalidate(need_id: UUID) -> None:
    await _cache().invalidate(need_id)


async def present_shortlist(need_id: UUID, query: ShortlistQuery) -> dict[str, Any] | None:
    return await _engine().present_shortlist(need_id, query)


async def candidate_card(need_id: UUID, candidate_id: UUID) -> dict[str, Any] | None:
    return await _engine().candidate_card(need_id, candidate_id)


def build_candidate_hints(
    candidate: CandidateFeatures,
    needs: list[NeedView],
    peers: list[CandidateFeatures] | None = None,
    today: Any = None,
) -> list[dict[str, Any]]:
    return _hints().build_candidate_hints(candidate, needs, peers or [], today=today)


def build_employer_hints(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return _hints().build_employer_hints(payload)


def apply_employer_hint(payload: dict[str, Any], hint: dict[str, Any]) -> list[dict[str, Any]]:
    return _hints().apply_employer_hint(payload, hint)


def project_shortlist(payload: dict[str, Any], query: ShortlistQuery) -> dict[str, Any]:
    return _project().project_shortlist(payload, query)


async def recompute_candidate(candidate_id: UUID) -> list[dict[str, Any]]:
    return await _engine().recompute_candidate(candidate_id)


async def recompute_employer(need_id: UUID) -> list[dict[str, Any]]:
    return await _engine().recompute_employer(need_id)


def shortlist_cache_key(need_id: UUID) -> str:
    return _cache().shortlist_key(need_id)
