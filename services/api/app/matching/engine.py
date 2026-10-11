"""Build a shortlist, cache it, and serve hints. Imported by the public facade at call time."""

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.exc import InterfaceError, OperationalError

from app.core.db import SessionLocal
from app.matching import cache, store
from app.matching.config import HINT_PEER_CAP, MUST_GATE
from app.matching.formulas import (
    drop_must_skill,
    match_percent,
    salary_passes,
    score_breakdown,
    split_ranked,
    utc_date,
    with_salary_to,
)
from app.matching.hints_algo import build_candidate_hints, build_employer_hints, text_gaps
from app.matching.project import category_tiles, project_shortlist
from app.matching.service import (
    CategoryTile,
    NeedView,
    ScoreBreakdown,
    Shortlist,
    ShortlistItem,
    ShortlistQuery,
    empty_shortlist,
)
from app.matching.store import LoadedPerson, NeedContext
from app.matching.taxonomy import allowed_specializations, specialization_title
from app.profile.service import FspFeature

logger = logging.getLogger(__name__)

_CONNECTION_ERRORS = (OperationalError, InterfaceError, OSError, ConnectionError, TimeoutError)

_GRADE_TITLES = {
    "intern": "Intern",
    "junior": "Junior",
    "middle": "Middle",
    "senior": "Senior",
    "lead": "Lead",
}


def initials_name(full_name: str) -> str:
    parts = [part for part in full_name.split() if part]
    if not parts:
        return "Кандидат"
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {parts[1][0]}."


def category_label(specialization: str | None, grade: str | None) -> str:
    title = specialization_title(specialization)
    if not grade:
        return title
    return f"{title} · {_GRADE_TITLES.get(grade, grade)}"


def fsp_badge(achievements: list[FspFeature]) -> dict[str, str] | None:
    if not achievements:
        return None
    ranked = sorted(achievements, key=lambda item: (item.place is None, item.place or 0, item.event))
    top = ranked[0]
    bits: list[str] = []
    if top.place:
        bits.append(f"{top.place} место")
    if top.event:
        bits.append(top.event)
    text = "ФСП · " + ", ".join(bits) if bits else "ФСП"
    return {"discipline": top.discipline, "text": text}


def person_row(person: LoadedPerson, breakdown: ScoreBreakdown, bucket: str, need: NeedView) -> dict[str, Any]:
    features = person.features
    tested = sorted({item.skill_id for item in features.skills if item.source == "test" and item.score is not None})
    skills = sorted({item.skill_id for item in features.skills})
    active = utc_date(features.last_active_at)
    domain_hit = bool(need.domain) and any(item.domain == need.domain for item in features.evidence)
    return {
        "candidate_id": features.candidate_id,
        "score": breakdown.s,
        "match": match_percent(breakdown.s),
        "specialization": features.specialization,
        "grade": features.grade,
        "formats": list(features.formats),
        "city": features.city,
        "display_name": initials_name(features.full_name),
        "experience_years": features.experience_years,
        "test_score": features.grade_score,
        "explanations": list(breakdown.explanations),
        "invitation_status": person.invitation_status,
        "favorite": person.favorite,
        "fsp_disciplines": [item.discipline for item in features.fsp],
        "fsp_badge": fsp_badge(features.fsp),
        "skills": skills,
        "tested_skills": tested,
        "last_active_at": None if active is None else active.isoformat(),
        "domain_hit": domain_hit,
        "bucket": bucket,
        "projects": list(person.projects),
        "category": category_label(features.specialization, features.grade),
        "factors": score_factors(breakdown),
        "must_coverage": [
            {"skill": skill, "value": _percent(breakdown.coverages.get(skill, 0.0))} for skill in need.must_skills
        ],
    }


def _percent(value: float | None) -> int:
    return max(0, min(100, int(round((value or 0.0) * 100))))


def score_factors(breakdown: ScoreBreakdown) -> dict[str, int]:
    """Employer-side features of S in percent, plus the candidate-side C as «conditions»."""
    features = breakdown.features
    return {
        "skills": _percent(features.get("must_cov")),
        "experience": _percent(features.get("ef")),
        "grade": _percent(features.get("grade_fit")),
        "tests": _percent(features.get("skill_avg")),
        "fsp": _percent(features.get("fsp")),
        "fresh": _percent(features.get("fresh")),
        "conditions": _percent(breakdown.c),
    }


def shortlist_from_payload(payload: dict[str, Any]) -> Shortlist:
    items: list[ShortlistItem] = []
    hidden: list[ShortlistItem] = []
    for row in payload.get("rows") or []:
        if row.get("bucket") not in {"main", "hidden"}:
            continue
        gated = row.get("bucket") == "hidden"
        breakdown = ScoreBreakdown(
            s=float(row.get("score") or 0.0),
            e=0.0,
            c=0.0,
            features={},
            explanations=list(row.get("explanations") or []),
            gated=gated,
        )
        target = hidden if gated else items
        target.append(
            ShortlistItem(
                candidate_id=str(row.get("candidate_id")),
                position=0,
                score=float(row.get("score") or 0.0),
                breakdown=breakdown,
                hidden_by_filter=gated,
            )
        )
    for group in (items, hidden):
        group.sort(key=lambda item: (-item.score, item.candidate_id))
        for index, item in enumerate(group, start=1):
            item.position = index
    main_rows = [row for row in payload.get("rows") or [] if row.get("bucket") == "main"]
    categories = [
        CategoryTile(id=str(tile["id"]), title=str(tile["title"]), count=int(tile["count"]))
        for tile in category_tiles(str(payload.get("specialization") or ""), main_rows)
    ]
    return Shortlist(
        need_id=str(payload.get("need_id")),
        items=items,
        hidden=hidden,
        categories=categories,
    )


async def _similarities(session: Any, need: NeedView, candidate_ids: list[UUID]) -> list[dict[UUID, float]]:
    found: list[dict[UUID, float]] = []
    for requirement in need.requirements:
        if not requirement.embedding or not any(component != 0.0 for component in requirement.embedding):
            continue
        found.append(await store.nearest_similarity(session, candidate_ids, requirement.embedding))
    return found


async def _compute(session: Any, ctx: NeedContext) -> dict[str, Any]:
    need = ctx.view
    specs = allowed_specializations(need.specialization)
    contenders = await store.filter_candidate_ids(session, need, specs)
    coverage = await store.coverage_by_candidate(session, contenders, list(need.must_skills))
    similarities = await _similarities(session, need, contenders)
    ranked = store.rank_candidate_ids(contenders, coverage, similarities)
    salary_ids = await store.salary_excluded_ids(session, need, specs)
    median = await store.category_salary_median(session, need)
    wanted = list(dict.fromkeys([*ranked, *salary_ids]))
    people = await store.load_people(session, wanted, UUID(need.id), UUID(ctx.company_id))

    scored: dict[UUID, ScoreBreakdown] = {}
    for candidate_id in ranked:
        person = people.get(candidate_id)
        if person is None:
            continue
        scored[candidate_id] = score_breakdown(need, person.features)
    pairs = [(str(candidate_id), breakdown.s, breakdown.gated) for candidate_id, breakdown in scored.items()]
    main_ids, hidden_ids = split_ranked(pairs)
    by_text = {str(candidate_id): candidate_id for candidate_id in scored}

    rows: list[dict[str, Any]] = []
    hidden_people: list[tuple[LoadedPerson, ScoreBreakdown]] = []
    for candidate_text in main_ids:
        candidate_id = by_text[candidate_text]
        person = people[candidate_id]
        breakdown = scored[candidate_id]
        rows.append(person_row(person, breakdown, "main", need))
    for candidate_text in hidden_ids:
        candidate_id = by_text[candidate_text]
        person = people[candidate_id]
        breakdown = scored[candidate_id]
        rows.append(person_row(person, breakdown, "hidden", need))
        hidden_people.append((person, breakdown))

    for person, breakdown in hidden_people:
        failing = [skill for skill in need.must_skills if breakdown.coverages.get(skill, 0.0) < MUST_GATE]
        if len(failing) != 1:
            continue
        skill = failing[0]
        alternative = score_breakdown(drop_must_skill(need, skill), person.features)
        if alternative.gated:
            continue
        rows.append(person_row(person, alternative, f"expand:{skill}", need))

    if median is not None and need.salary_to < median:
        raised = with_salary_to(need, median)
        for candidate_id in salary_ids:
            person = people.get(candidate_id)
            if person is None or str(candidate_id) in set(main_ids):
                continue
            minimum = person.features.min_salary
            if minimum is None or not salary_passes(median, minimum):
                continue
            alternative = score_breakdown(raised, person.features)
            if alternative.gated:
                continue
            rows.append(person_row(person, alternative, "salary", need))

    return {
        "need_id": need.id,
        "company_id": ctx.company_id,
        "specialization": need.specialization,
        "domain": need.domain,
        "must_skills": list(need.must_skills),
        "description": need.description,
        "text_gaps": text_gaps(need.description, need.requirements),
        "salary_median": median if median is not None and need.salary_to < median else None,
        "rows": rows,
    }


async def get_payload(need_id: UUID) -> dict[str, Any] | None:
    cached = await cache.cache_get(need_id)
    if cached is not None:
        return cached
    async with SessionLocal() as session:
        ctx = await store.load_need(session, need_id)
        if ctx is None:
            return None
        payload = await _compute(session, ctx)
    await cache.cache_set(need_id, payload)
    return payload


async def build_shortlist(need_id: UUID) -> Shortlist:
    payload = await get_payload(need_id)
    if payload is None:
        return empty_shortlist(need_id)
    return shortlist_from_payload(payload)


async def _refresh(payload: dict[str, Any]) -> None:
    company_raw = payload.get("company_id")
    need_raw = payload.get("need_id")
    if not company_raw or not need_raw:
        return
    candidate_ids: list[UUID] = []
    for row in payload.get("rows") or []:
        try:
            candidate_ids.append(UUID(str(row["candidate_id"])))
        except (KeyError, ValueError):
            continue
    try:
        async with SessionLocal() as session:
            favorites, invitations = await store.refresh_flags(
                session,
                UUID(str(company_raw)),
                UUID(str(need_raw)),
                candidate_ids,
            )
    except _CONNECTION_ERRORS:
        logger.warning("shortlist flag refresh skipped", exc_info=True)
        return
    for row in payload.get("rows") or []:
        candidate_id = str(row.get("candidate_id"))
        row["favorite"] = candidate_id in favorites
        row["invitation_status"] = invitations.get(candidate_id)


async def present_shortlist(need_id: UUID, query: ShortlistQuery) -> dict[str, Any] | None:
    payload = await get_payload(need_id)
    if payload is None:
        return None
    await _refresh(payload)
    return project_shortlist(payload, query)


async def candidate_card(need_id: UUID, candidate_id: UUID) -> dict[str, Any] | None:
    async with SessionLocal() as session:
        ctx = await store.load_need(session, need_id)
        if ctx is None:
            return None
        people = await store.load_people(session, [candidate_id], need_id, UUID(ctx.company_id))
    person = people.get(candidate_id)
    if person is None:
        return None
    breakdown = score_breakdown(ctx.view, person.features)
    row = person_row(person, breakdown, "card", ctx.view)
    return {
        "candidate_id": row["candidate_id"],
        "display_name": row["display_name"],
        "full_name_initials": row["display_name"],
        "category": row["category"],
        "city": row["city"],
        "experience_years": row["experience_years"],
        "match": row["match"],
        "test_score": row["test_score"],
        "explanations": row["explanations"],
        "skills": row["skills"],
        "projects": row["projects"],
        "fsp_badge": row["fsp_badge"],
        "invitation_status": row["invitation_status"],
    }


async def recompute_candidate(candidate_id: UUID) -> list[dict[str, Any]]:
    await cache.invalidate_candidate(candidate_id)
    async with SessionLocal() as session:
        people = await store.load_people(session, [candidate_id], None, None)
        person = people.get(candidate_id)
        if person is None:
            return []
        needs = await store.load_open_needs(session, person.features.specialization)
        peer_ids = await store.load_peer_ids(
            session,
            person.features.specialization,
            person.features.grade,
            candidate_id,
            HINT_PEER_CAP,
        )
        peers = await store.load_people(session, peer_ids, None, None)
    hints = build_candidate_hints(
        person.features,
        needs,
        [item.features for item in peers.values()],
    )
    await cache.hints_set(cache.candidate_hint_key(candidate_id), hints)
    return hints


async def recompute_employer(need_id: UUID) -> list[dict[str, Any]]:
    cached = await cache.hints_get(cache.employer_hint_key(need_id))
    if cached is not None:
        return cached
    payload = await get_payload(need_id)
    if payload is None:
        return []
    hints = build_employer_hints(payload)
    await cache.hints_set(cache.employer_hint_key(need_id), hints)
    return hints
