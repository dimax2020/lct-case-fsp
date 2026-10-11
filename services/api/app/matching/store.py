"""SQL filters from §6.1. Models stay in their modules; this file talks to tables by name."""

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import String, bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.exc import DataError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.matching.config import (
    CANDIDATE_POOL_STATUSES,
    COVERAGE_FSP,
    COVERAGE_PROJECT,
    COVERAGE_RESUME,
    OPEN_INVITE_STATUSES,
    SALARY_FLOOR_RATIO,
    SHORTLIST_CAP,
    TEST_SCORE_MAX,
    TOP_EVIDENCE,
)
from app.matching.formulas import grade_window, usable_embedding
from app.matching.service import NeedView, RequirementView
from app.profile.service import CandidateFeatures, EvidenceFeature, FspFeature, SkillFeature

logger = logging.getLogger(__name__)

_UUIDS = ARRAY(PG_UUID(as_uuid=True))
_STRINGS = ARRAY(String())

_GRADE_CASE = """
CASE c.grade
  WHEN 'intern' THEN 0
  WHEN 'junior' THEN 1
  WHEN 'middle' THEN 2
  WHEN 'senior' THEN 3
  WHEN 'lead' THEN 4
  ELSE NULL
END
"""


@dataclass
class NeedContext:
    view: NeedView
    company_id: str
    status: str


@dataclass
class LoadedPerson:
    features: CandidateFeatures
    projects: list[str]
    invitation_status: str | None
    favorite: bool


def _uuid(value: Any) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def parse_vector(value: Any) -> list[float] | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return [float(item) for item in value]
    text_value = str(value).strip()
    if text_value.startswith("[") and text_value.endswith("]"):
        text_value = text_value[1:-1]
    if not text_value:
        return None
    return [float(part) for part in text_value.split(",") if part.strip()]


def _vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(f"{component:.8f}" for component in embedding) + "]"


def _as_list(value: Any) -> list[str]:
    if not value:
        return []
    return [str(item) for item in value]


async def load_need(session: AsyncSession, need_id: UUID) -> NeedContext | None:
    result = await session.execute(
        text(
            """
            SELECT n.id, n.company_id, n.specialization, n.grades, n.salary_from, n.salary_to,
                   n.formats, n.city, n.must_skills, n.nice_skills, n.description, n.domain,
                   n.stages, n.status, co.benefits
            FROM needs n
            LEFT JOIN companies co ON co.id = n.company_id
            WHERE n.id = :need_id
            """
        ),
        {"need_id": need_id},
    )
    row = result.mappings().first()
    if row is None:
        return None
    requirements = await _load_requirements(session, need_id)
    view = NeedView(
        id=str(row["id"]),
        specialization=str(row["specialization"]),
        grades=_as_list(row["grades"]),
        salary_from=int(row["salary_from"]),
        salary_to=int(row["salary_to"]),
        formats=_as_list(row["formats"]),
        city=row["city"],
        must_skills=_as_list(row["must_skills"]),
        nice_skills=_as_list(row["nice_skills"]),
        domain=row["domain"],
        stages=int(row["stages"]),
        benefits=_as_list(row["benefits"]),
        requirements=requirements,
        description=str(row["description"] or ""),
    )
    return NeedContext(view=view, company_id=str(row["company_id"]), status=str(row["status"]))


async def _load_requirements(session: AsyncSession, need_id: UUID) -> list[RequirementView]:
    result = await session.execute(
        text(
            """
            SELECT id, task, domain, skills, scale, kind, embedding::text AS embedding
            FROM need_requirements
            WHERE need_id = :need_id
            ORDER BY id
            """
        ),
        {"need_id": need_id},
    )
    views: list[RequirementView] = []
    for row in result.mappings():
        views.append(
            RequirementView(
                id=str(row["id"]),
                task=str(row["task"]),
                domain=row["domain"],
                skills=_as_list(row["skills"]),
                scale=row["scale"],
                kind=str(row["kind"]),
                embedding=parse_vector(row["embedding"]),
            )
        )
    return views


def _filter_sql(salary_clause: str) -> str:
    return f"""
        SELECT c.id
        FROM candidates c
        WHERE c.visible IS TRUE
          AND c.status = ANY(:statuses)
          AND c.specialization = ANY(:specs)
          AND ({_GRADE_CASE}) BETWEEN :lo AND :hi
          AND {salary_clause}
          AND (
            c.formats && :formats
            OR (:hybrid_for_remote AND 'remote' = ANY(c.formats))
          )
          AND (
            CAST(:domain AS varchar) IS NULL
            OR NOT (CAST(:domain AS varchar) = ANY(COALESCE(c.blocked_domains, ARRAY[]::varchar[])))
          )
        ORDER BY c.id
    """


def _filter_statement(sql: str) -> Any:
    return text(sql).bindparams(
        bindparam("statuses", type_=_STRINGS),
        bindparam("specs", type_=_STRINGS),
        bindparam("formats", type_=_STRINGS),
    )


def _filter_params(need: NeedView, specs: list[str]) -> dict[str, Any] | None:
    window = grade_window(need.grades)
    if window is None:
        return None
    low, high = window
    return {
        "statuses": list(CANDIDATE_POOL_STATUSES),
        "specs": specs,
        "lo": low,
        "hi": high,
        "salary_to": need.salary_to,
        "floor": SALARY_FLOOR_RATIO,
        "formats": list(need.formats),
        "hybrid_for_remote": "hybrid" in set(need.formats),
        "domain": need.domain,
    }


async def filter_candidate_ids(session: AsyncSession, need: NeedView, specs: list[str]) -> list[UUID]:
    params = _filter_params(need, specs)
    if params is None:
        return []
    sql = _filter_sql("(c.min_salary IS NULL OR :salary_to >= c.min_salary * :floor)")
    result = await session.execute(_filter_statement(sql), params)
    return [_uuid(row[0]) for row in result]


async def salary_excluded_ids(session: AsyncSession, need: NeedView, specs: list[str]) -> list[UUID]:
    params = _filter_params(need, specs)
    if params is None:
        return []
    sql = _filter_sql("(c.min_salary IS NOT NULL AND NOT (:salary_to >= c.min_salary * :floor))")
    result = await session.execute(_filter_statement(sql), params)
    return [_uuid(row[0]) for row in result][:SHORTLIST_CAP]


async def category_salary_median(session: AsyncSession, need: NeedView) -> int | None:
    result = await session.execute(
        text(
            f"""
            SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY c.min_salary) AS median
            FROM candidates c
            WHERE c.visible IS TRUE
              AND c.status = ANY(:statuses)
              AND c.specialization = :spec
              AND c.grade = ANY(:grades)
              AND c.min_salary IS NOT NULL
              AND ({_GRADE_CASE}) IS NOT NULL
            """
        ).bindparams(
            bindparam("statuses", type_=_STRINGS),
            bindparam("grades", type_=_STRINGS),
        ),
        {
            "statuses": list(CANDIDATE_POOL_STATUSES),
            "spec": need.specialization,
            "grades": list(need.grades),
        },
    )
    median = result.scalar_one_or_none()
    if median is None:
        return None
    return int(round(float(median)))


async def coverage_by_candidate(
    session: AsyncSession,
    candidate_ids: list[UUID],
    must_skills: list[str],
) -> dict[UUID, float]:
    if not candidate_ids or not must_skills:
        return {candidate_id: 0.0 for candidate_id in candidate_ids}
    result = await session.execute(
        text(
            """
            SELECT s.candidate_id, s.skill_id,
                   MAX(
                     CASE
                       WHEN s.source = 'test'
                         THEN LEAST(GREATEST(COALESCE(s.score, 0), 0) / :score_max, 1.0)
                       WHEN s.source = 'resume' THEN :cov_resume
                       WHEN s.source = 'project' THEN :cov_project
                       WHEN s.source = 'fsp_id' THEN :cov_fsp
                       ELSE 0
                     END
                   ) AS best
            FROM candidate_skills s
            WHERE s.candidate_id = ANY(:ids)
              AND s.skill_id = ANY(:must)
            GROUP BY s.candidate_id, s.skill_id
            """
        ).bindparams(
            bindparam("ids", type_=_UUIDS),
            bindparam("must", type_=_STRINGS),
        ),
        {
            "ids": candidate_ids,
            "must": must_skills,
            "score_max": TEST_SCORE_MAX,
            "cov_resume": COVERAGE_RESUME,
            "cov_project": COVERAGE_PROJECT,
            "cov_fsp": COVERAGE_FSP,
        },
    )
    totals: dict[UUID, float] = {candidate_id: 0.0 for candidate_id in candidate_ids}
    for row in result.mappings():
        candidate_id = _uuid(row["candidate_id"])
        totals[candidate_id] = totals.get(candidate_id, 0.0) + float(row["best"] or 0.0)
    count = float(len(must_skills))
    return {candidate_id: value / count for candidate_id, value in totals.items()}


async def nearest_similarity(
    session: AsyncSession,
    candidate_ids: list[UUID],
    embedding: list[float],
) -> dict[UUID, float]:
    if not candidate_ids or not usable_embedding(embedding):
        return {}
    limit = max(len(candidate_ids), 1) * TOP_EVIDENCE * 4
    try:
        result = await session.execute(
            text(
                """
                SELECT e.candidate_id,
                       1 - (e.embedding <=> CAST(:vec AS vector)) AS sim
                FROM evidence_units e
                WHERE e.embedding IS NOT NULL
                  AND e.candidate_id = ANY(:ids)
                ORDER BY e.embedding <=> CAST(:vec AS vector)
                LIMIT :limit
                """
            ).bindparams(bindparam("ids", type_=_UUIDS)),
            {"ids": candidate_ids, "vec": _vector_literal(embedding), "limit": limit},
        )
    except (ProgrammingError, DataError):
        logger.warning("pgvector neighbour query skipped", exc_info=True)
        await session.rollback()
        return {}
    best: dict[UUID, float] = {}
    for row in result.mappings():
        similarity = row["sim"]
        if similarity is None:
            continue
        value = float(similarity)
        if value != value:
            continue
        candidate_id = _uuid(row["candidate_id"])
        best[candidate_id] = max(best.get(candidate_id, value), value)
    return best


def rank_candidate_ids(
    candidate_ids: list[UUID],
    coverage: dict[UUID, float],
    similarities: list[dict[UUID, float]],
) -> list[UUID]:
    def sort_key(candidate_id: UUID) -> tuple[float, str]:
        bonus = 0.0
        if similarities:
            bonus = sum(item.get(candidate_id, 0.0) for item in similarities) / len(similarities)
        return (-(coverage.get(candidate_id, 0.0) + bonus), str(candidate_id))

    return sorted(candidate_ids, key=sort_key)[:SHORTLIST_CAP]


async def load_people(
    session: AsyncSession,
    candidate_ids: list[UUID],
    need_id: UUID | None,
    company_id: UUID | None,
) -> dict[UUID, LoadedPerson]:
    if not candidate_ids:
        return {}
    result = await session.execute(
        text(
            """
            SELECT c.id, c.full_name, c.specialization, c.grade, c.grade_score, c.min_salary,
                   c.formats, c.status, c.visible, c.city, c.liked_skills, c.disliked_skills,
                   c.liked_domains, c.blocked_domains, c.last_active_at,
                   (
                     SELECT COUNT(*)
                     FROM invitations i
                     WHERE i.candidate_id = c.id AND i.status = ANY(:open_statuses)
                   ) AS open_invites
            FROM candidates c
            WHERE c.id = ANY(:ids)
            """
        ).bindparams(
            bindparam("ids", type_=_UUIDS),
            bindparam("open_statuses", type_=_STRINGS),
        ),
        {"ids": candidate_ids, "open_statuses": list(OPEN_INVITE_STATUSES)},
    )
    rows = list(result.mappings())
    skills = await _grouped(session, candidate_ids, "candidate_skills", "skill_id, score, source")
    evidence = await _evidence(session, candidate_ids)
    achievements = await _grouped(session, candidate_ids, "fsp_achievements", "discipline, event, place, year")
    projects = await _grouped(session, candidate_ids, "projects", "task")
    years = await _experience_years(session, candidate_ids)
    invitations = await _invitation_status(session, candidate_ids, need_id)
    favorites = await _favorites(session, candidate_ids, company_id)
    loaded: dict[UUID, LoadedPerson] = {}
    for row in rows:
        candidate_id = _uuid(row["id"])
        skill_rows = skills.get(candidate_id, [])
        evidence_rows = evidence.get(candidate_id, [])
        fsp_rows = achievements.get(candidate_id, [])
        project_rows = [str(item["task"]) for item in projects.get(candidate_id, []) if item.get("task")]
        if not project_rows:
            project_rows = [item.task for item in evidence_rows if item.origin == "project" and item.task]
        features = CandidateFeatures(
            candidate_id=str(candidate_id),
            full_name=str(row["full_name"] or ""),
            display_name="",
            specialization=row["specialization"],
            grade=row["grade"],
            grade_score=None if row["grade_score"] is None else float(row["grade_score"]),
            min_salary=None if row["min_salary"] is None else int(row["min_salary"]),
            formats=_as_list(row["formats"]),
            status=str(row["status"]),
            visible=bool(row["visible"]),
            city=row["city"],
            liked_skills=_as_list(row["liked_skills"]),
            disliked_skills=_as_list(row["disliked_skills"]),
            liked_domains=_as_list(row["liked_domains"]),
            blocked_domains=_as_list(row["blocked_domains"]),
            last_active_at=row["last_active_at"] if isinstance(row["last_active_at"], datetime) else None,
            skills=[
                SkillFeature(
                    skill_id=str(item["skill_id"]),
                    score=None if item["score"] is None else float(item["score"]),
                    source=str(item["source"]),
                )
                for item in skill_rows
            ],
            evidence=evidence_rows,
            fsp=[
                FspFeature(
                    discipline=str(item["discipline"]),
                    event=str(item["event"]),
                    place=None if item["place"] is None else int(item["place"]),
                    year=None if item["year"] is None else int(item["year"]),
                )
                for item in fsp_rows
            ],
            open_invites=int(row["open_invites"] or 0),
            experience_years=years.get(candidate_id),
        )
        loaded[candidate_id] = LoadedPerson(
            features=features,
            projects=project_rows,
            invitation_status=invitations.get(candidate_id),
            favorite=candidate_id in favorites,
        )
    return loaded


async def _grouped(
    session: AsyncSession,
    candidate_ids: list[UUID],
    table: str,
    columns: str,
) -> dict[UUID, list[Any]]:
    if table not in {"candidate_skills", "fsp_achievements", "projects"}:
        return {}
    result = await session.execute(
        text(f"SELECT candidate_id, {columns} FROM {table} WHERE candidate_id = ANY(:ids)").bindparams(
            bindparam("ids", type_=_UUIDS)
        ),
        {"ids": candidate_ids},
    )
    grouped: dict[UUID, list[Any]] = {}
    for row in result.mappings():
        grouped.setdefault(_uuid(row["candidate_id"]), []).append(row)
    return grouped


async def _evidence(session: AsyncSession, candidate_ids: list[UUID]) -> dict[UUID, list[EvidenceFeature]]:
    result = await session.execute(
        text(
            """
            SELECT id, candidate_id, origin, task, domain, skills, role, "date" AS occurred_on,
                   trust, evidence_span, embedding::text AS embedding
            FROM evidence_units
            WHERE candidate_id = ANY(:ids)
            """
        ).bindparams(bindparam("ids", type_=_UUIDS)),
        {"ids": candidate_ids},
    )
    grouped: dict[UUID, list[EvidenceFeature]] = {}
    for row in result.mappings():
        occurred = row["occurred_on"]
        if isinstance(occurred, datetime):
            occurred_on: date | None = occurred.date()
        elif isinstance(occurred, date):
            occurred_on = occurred
        else:
            occurred_on = None
        feature = EvidenceFeature(
            id=str(row["id"]),
            task=str(row["task"]),
            domain=row["domain"],
            skills=_as_list(row["skills"]),
            role=str(row["role"] or "participant"),
            date=occurred_on,
            trust=float(row["trust"] or 0.0),
            embedding=parse_vector(row["embedding"]),
            origin=str(row["origin"]),
            evidence_span=row["evidence_span"],
        )
        grouped.setdefault(_uuid(row["candidate_id"]), []).append(feature)
    return grouped


async def _experience_years(session: AsyncSession, candidate_ids: list[UUID]) -> dict[UUID, float]:
    result = await session.execute(
        text(
            """
            SELECT candidate_id,
                   EXTRACT(EPOCH FROM (
                     COALESCE(MAX(COALESCE(e."end", CURRENT_DATE)), CURRENT_DATE) - MIN(e.start)
                   )) / 31557600.0 AS years
            FROM experiences e
            WHERE e.candidate_id = ANY(:ids) AND e.start IS NOT NULL
            GROUP BY candidate_id
            """
        ).bindparams(bindparam("ids", type_=_UUIDS)),
        {"ids": candidate_ids},
    )
    found: dict[UUID, float] = {}
    for row in result.mappings():
        if row["years"] is None:
            continue
        found[_uuid(row["candidate_id"])] = round(float(row["years"]), 2)
    return found


async def _invitation_status(
    session: AsyncSession,
    candidate_ids: list[UUID],
    need_id: UUID | None,
) -> dict[UUID, str]:
    if need_id is None:
        return {}
    result = await session.execute(
        text(
            """
            SELECT candidate_id, status
            FROM invitations
            WHERE need_id = :need_id AND candidate_id = ANY(:ids)
            """
        ).bindparams(bindparam("ids", type_=_UUIDS)),
        {"need_id": need_id, "ids": candidate_ids},
    )
    return {_uuid(row["candidate_id"]): str(row["status"]) for row in result.mappings()}


async def _favorites(
    session: AsyncSession,
    candidate_ids: list[UUID],
    company_id: UUID | None,
) -> set[UUID]:
    if company_id is None:
        return set()
    result = await session.execute(
        text(
            """
            SELECT candidate_id
            FROM favorites
            WHERE company_id = :company_id AND candidate_id = ANY(:ids)
            """
        ).bindparams(bindparam("ids", type_=_UUIDS)),
        {"company_id": company_id, "ids": candidate_ids},
    )
    return {_uuid(row["candidate_id"]) for row in result.mappings()}


async def refresh_flags(
    session: AsyncSession,
    company_id: UUID,
    need_id: UUID,
    candidate_ids: list[UUID],
) -> tuple[set[str], dict[str, str]]:
    if not candidate_ids:
        return set(), {}
    favorites = await _favorites(session, candidate_ids, company_id)
    invitations = await _invitation_status(session, candidate_ids, need_id)
    return {str(item) for item in favorites}, {str(key): value for key, value in invitations.items()}


async def load_open_needs(session: AsyncSession, specialization: str | None) -> list[NeedView]:
    if not specialization:
        return []
    result = await session.execute(
        text(
            """
            SELECT n.id
            FROM needs n
            WHERE n.status = 'open' AND n.specialization = :spec
            ORDER BY n.id
            """
        ),
        {"spec": specialization},
    )
    views: list[NeedView] = []
    for row in result:
        ctx = await load_need(session, _uuid(row[0]))
        if ctx is not None:
            views.append(ctx.view)
    return views


async def load_peer_ids(
    session: AsyncSession,
    specialization: str | None,
    grade: str | None,
    exclude: UUID,
    limit: int,
) -> list[UUID]:
    if not specialization or not grade:
        return []
    result = await session.execute(
        text(
            """
            SELECT c.id
            FROM candidates c
            WHERE c.specialization = :spec
              AND c.grade = :grade
              AND c.visible IS TRUE
              AND c.status = ANY(:statuses)
              AND c.id <> :exclude
            ORDER BY c.id
            LIMIT :limit
            """
        ).bindparams(bindparam("statuses", type_=_STRINGS)),
        {
            "spec": specialization,
            "grade": grade,
            "statuses": list(CANDIDATE_POOL_STATUSES),
            "exclude": exclude,
            "limit": limit,
        },
    )
    return [_uuid(row[0]) for row in result]
