"""Apply POOL-3/POOL-4 to a cached shortlist. No database and no rescoring."""

import re
from datetime import UTC, date, datetime
from typing import Any

from app.matching.config import ACTIVE_WINDOW_DAYS, NEIGHBOR_CATEGORIES
from app.matching.hints_algo import apply_employer_hint, build_employer_hints
from app.matching.service import ShortlistQuery
from app.matching.taxonomy import allowed_specializations, specialization_title


def _today() -> date:
    return datetime.now(UTC).date()


def active_within(raw: str | None, days: int, today: date) -> bool:
    if not raw:
        return False
    try:
        moment = date.fromisoformat(str(raw)[:10])
    except ValueError:
        return False
    return (today - moment).days <= days


def stack_matches(skills: list[str], query: str) -> bool:
    tokens = [token for token in re.split(r"[\s,]+", query.lower()) if token]
    if not tokens:
        return True
    haystack = [skill.lower() for skill in skills]
    return all(any(token in skill for skill in haystack) for token in tokens)


def pool_filters(row: dict[str, Any], query: ShortlistQuery, today: date) -> bool:
    if query.only_fsp and not row.get("fsp_disciplines"):
        return False
    if query.fsp_discipline and query.fsp_discipline not in set(row.get("fsp_disciplines") or []):
        return False
    if query.min_test_score is not None:
        score = row.get("test_score")
        if score is None or float(score) < query.min_test_score:
            return False
    if query.stack and not stack_matches(list(row.get("skills") or []), query.stack):
        return False
    if query.work_format:
        formats = {str(item).lower() for item in row.get("formats") or []}
        if query.work_format.lower() not in formats:
            return False
    if query.active_30d and not active_within(row.get("last_active_at"), ACTIVE_WINDOW_DAYS, today):
        return False
    return True


def category_tiles(specialization: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for row in rows:
        spec = row.get("specialization")
        if spec:
            counts[str(spec)] = counts.get(str(spec), 0) + 1
    tiles = []
    for spec in allowed_specializations(specialization)[:NEIGHBOR_CATEGORIES]:
        tiles.append({"id": spec, "title": specialization_title(spec), "count": counts.get(spec, 0)})
    return tiles


def _public_item(row: dict[str, Any], position: int) -> dict[str, Any]:
    return {
        "position": position,
        "candidate_id": row.get("candidate_id"),
        "display_name": row.get("display_name"),
        "category": row.get("category"),
        "grade": row.get("grade"),
        "experience_years": row.get("experience_years"),
        "city": row.get("city"),
        "fsp_badge": row.get("fsp_badge"),
        "match": row.get("match"),
        "test_score": row.get("test_score"),
        "explanations": list(row.get("explanations") or []),
        "invitation_status": row.get("invitation_status"),
        "favorite": bool(row.get("favorite")),
    }


def project_shortlist(payload: dict[str, Any], query: ShortlistQuery, today: date | None = None) -> dict[str, Any]:
    moment = today or _today()
    rows = list(payload.get("rows") or [])
    main = [row for row in rows if row.get("bucket") == "main"]
    hidden = [row for row in rows if row.get("bucket") == "hidden"]
    specialization = str(payload.get("specialization") or "")
    tiled = [row for row in main if pool_filters(row, query, moment)]
    categories = category_tiles(specialization, tiled)

    if query.tab == "hidden":
        chosen = [row for row in hidden if pool_filters(row, query, moment)]
    elif query.hint_id:
        hints = build_employer_hints(payload, moment)
        hint = next((item for item in hints if item.get("id") == query.hint_id), None)
        base = apply_employer_hint(payload, hint, moment) if hint and hint.get("apply") else main
        chosen = [row for row in base if pool_filters(row, query, moment)]
    else:
        chosen = list(tiled)

    if query.category:
        chosen = [row for row in chosen if row.get("specialization") == query.category]
    if query.tab == "favorites":
        chosen = [row for row in chosen if row.get("favorite")]

    chosen.sort(key=lambda row: (-float(row.get("score") or 0.0), str(row.get("candidate_id"))))
    hidden_count_rows = [row for row in hidden if pool_filters(row, query, moment)]
    if query.category:
        hidden_count_rows = [row for row in hidden_count_rows if row.get("specialization") == query.category]

    page = query.page if query.page > 0 else 1
    page_size = query.page_size
    if page_size < 1:
        page_size = 1
    if page_size > 100:
        page_size = 100
    items = [_public_item(row, index) for index, row in enumerate(chosen, start=1)]
    start = (page - 1) * page_size
    hidden_count = len(chosen) if query.tab == "hidden" else len(hidden_count_rows)
    return {
        "need_id": payload.get("need_id"),
        "total": len(chosen),
        "page": page,
        "page_size": page_size,
        "categories": categories,
        "items": items[start : start + page_size],
        "hidden_count": hidden_count,
    }
