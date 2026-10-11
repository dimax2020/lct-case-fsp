"""Hint numbers match the list after the same filter is applied."""

from datetime import UTC, date, datetime, timedelta

from app.hints.service import apply_employer_hint, build_candidate_hints, build_employer_hints
from app.matching.project import project_shortlist
from app.matching.service import NeedView, ShortlistQuery
from app.profile.service import CandidateFeatures, SkillFeature


def _row(
    index: int,
    *,
    match: int,
    tested: bool,
    bucket: str = "main",
    specialization: str = "backend",
    favorite: bool = False,
    fsp: bool = False,
    active: str | None = None,
    domain_hit: bool = False,
) -> dict[str, object]:
    return {
        "candidate_id": f"{index:04d}",
        "score": match / 100,
        "match": match,
        "specialization": specialization,
        "grade": "middle",
        "formats": ["remote"],
        "city": "Новосибирск",
        "display_name": f"Кандидат {index}",
        "experience_years": 3,
        "test_score": 80,
        "explanations": ["Тест: Go 80/100"],
        "invitation_status": None,
        "favorite": favorite,
        "fsp_disciplines": ["algo"] if fsp else [],
        "fsp_badge": {"discipline": "algo", "text": "ФСП"} if fsp else None,
        "skills": ["go", "kafka"] if tested else ["go"],
        "tested_skills": ["kafka"] if tested else [],
        "last_active_at": active,
        "domain_hit": domain_hit,
        "bucket": bucket,
        "projects": [],
        "category": "Backend · Middle",
    }


def _payload(rows: list[dict[str, object]], **extra: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "need_id": "need-1",
        "company_id": "company-1",
        "specialization": "backend",
        "domain": "fintech",
        "must_skills": ["kafka", "go"],
        "description": "x" * 300,
        "text_gaps": [],
        "salary_median": None,
        "rows": rows,
    }
    payload.update(extra)
    return payload


def _mean(rows: list[dict[str, object]]) -> int:
    return int(round(sum(int(row["match"]) for row in rows) / len(rows)))


def test_narrow_hint_numbers_match_the_filtered_list() -> None:
    rows = [_row(index, match=95 if index < 9 else 80, tested=index < 9) for index in range(24)]
    payload = _payload(rows)
    hints = build_employer_hints(payload)
    hint = next(item for item in hints if item["id"] == "narrow:tested:kafka")
    manual = [row for row in rows if "kafka" in row["tested_skills"]]
    assert hint["before"] == 24
    assert hint["after"] == len(manual) == 9
    assert hint["avg_before"] == _mean(rows)
    assert hint["avg_after"] == _mean(manual)
    assert f"{hint['before']} → {hint['after']}" in hint["title"]
    assert f"{int(hint['avg_before'])} %" in hint["title"]
    assert f"{int(hint['avg_after'])} %" in hint["title"]
    applied = apply_employer_hint(payload, hint)
    assert len(applied) == hint["after"]
    assert _mean(applied) == hint["avg_after"]
    projected = project_shortlist(payload, ShortlistQuery(hint_id=hint["id"]))
    assert projected["total"] == hint["after"]
    assert "email" not in projected["items"][0]
    assert "phone" not in projected["items"][0]


def test_expand_and_salary_counts_match_added_rows() -> None:
    main = [_row(index, match=80, tested=True) for index in range(10)]
    expanded = [_row(100 + index, match=70, tested=False, bucket="expand:kubernetes") for index in range(40)]
    salary = [_row(200 + index, match=60, tested=True, bucket="salary") for index in range(15)]
    payload = _payload(
        [*main, *expanded, *salary],
        must_skills=["kubernetes"],
        salary_median=300_000,
        text_gaps=["scale"],
    )
    hints = build_employer_hints(payload)
    assert {item["type"] for item in hints} == {"expand", "salary", "text"}
    expand = next(item for item in hints if item["type"] == "expand")
    assert expand["before"] == 10
    assert expand["after"] == 50
    assert len(apply_employer_hint(payload, expand)) == expand["after"]
    assert "+40" in expand["title"]
    salary_hint = next(item for item in hints if item["type"] == "salary")
    assert salary_hint["after"] == salary_hint["before"] + 15
    assert len(apply_employer_hint(payload, salary_hint)) == salary_hint["after"]
    assert "300 000" in salary_hint["title"]
    assert len({item["type"] for item in hints}) == len(hints)
    assert len(hints) <= 3


def test_narrow_hint_requires_a_pool_of_five_and_a_higher_average() -> None:
    small = [_row(index, match=90, tested=index < 4) for index in range(10)]
    assert all(item["type"] != "narrow" for item in build_employer_hints(_payload(small, must_skills=["kafka"])))
    flat = [_row(index, match=80, tested=index < 8) for index in range(10)]
    assert all(item["type"] != "narrow" for item in build_employer_hints(_payload(flat, must_skills=["kafka"])))


def test_text_hint_when_the_pool_has_nothing_else() -> None:
    hints = build_employer_hints(_payload([], must_skills=[], text_gaps=["scale"], salary_median=None))
    assert [item["type"] for item in hints] == ["text"]
    assert "масштаб" in hints[0]["title"].lower()


def test_shortlist_filters_pagination_and_neighbor_tiles() -> None:
    today = date(2026, 10, 11)
    rows = []
    for index in range(5):
        rows.append(
            _row(
                index,
                match=90 - index,
                tested=True,
                specialization="backend" if index < 3 else "devops",
                favorite=index == 0,
                fsp=index < 2,
                active=(today - timedelta(days=1)).isoformat() if index < 4 else "2026-01-01",
            )
        )
    rows.append(_row(9, match=10, tested=False, bucket="hidden", fsp=True))
    payload = _payload(rows)
    page = project_shortlist(payload, ShortlistQuery(page=2, page_size=2), today)
    assert page["total"] == 5
    assert [item["position"] for item in page["items"]] == [3, 4]
    assert [item["candidate_id"] for item in page["items"]] == ["0002", "0003"]
    tiles = {tile["id"]: tile for tile in page["categories"]}
    assert tiles["backend"]["count"] == 3
    assert tiles["devops"]["count"] == 2
    assert "frontend" in tiles
    assert len(page["categories"]) == 3
    only_fsp = project_shortlist(payload, ShortlistQuery(only_fsp=True), today)
    assert only_fsp["total"] == 2
    favorites = project_shortlist(payload, ShortlistQuery(tab="favorites"), today)
    assert [item["candidate_id"] for item in favorites["items"]] == ["0000"]
    hidden = project_shortlist(payload, ShortlistQuery(tab="hidden"), today)
    assert hidden["total"] == 1
    assert hidden["hidden_count"] == 1
    fresh = project_shortlist(payload, ShortlistQuery(active_30d=True), today)
    assert fresh["total"] == 4
    stack = project_shortlist(payload, ShortlistQuery(stack="kafka"), today)
    assert stack["total"] == 5
    narrowed = project_shortlist(payload, ShortlistQuery(category="devops"), today)
    assert narrowed["total"] == 2
    assert narrowed["categories"][0]["count"] == 3


def _person(**overrides: object) -> CandidateFeatures:
    data: dict[str, object] = {
        "candidate_id": "cand",
        "full_name": "Мария Соколова",
        "display_name": "Мария С.",
        "specialization": "backend",
        "grade": "middle",
        "grade_score": 80.0,
        "min_salary": 300_000,
        "formats": ["remote"],
        "status": "seeking",
        "visible": True,
        "city": None,
        "liked_skills": ["go"],
        "disliked_skills": [],
        "liked_domains": [],
        "blocked_domains": [],
        "last_active_at": datetime(2026, 10, 11, tzinfo=UTC),
        "skills": [SkillFeature(skill_id="go", score=100, source="test")],
        "evidence": [],
        "fsp": [],
        "open_invites": 0,
        "experience_years": 3.0,
    }
    data.update(overrides)
    return CandidateFeatures(**data)  # type: ignore[arg-type]


def _need(**overrides: object) -> NeedView:
    data: dict[str, object] = {
        "id": "n",
        "specialization": "backend",
        "grades": ["middle"],
        "salary_from": 200_000,
        "salary_to": 500_000,
        "formats": ["remote"],
        "city": None,
        "must_skills": ["go"],
        "nice_skills": [],
        "domain": "fintech",
        "stages": 2,
        "benefits": [],
        "requirements": [],
        "description": "",
    }
    data.update(overrides)
    return NeedView(**data)  # type: ignore[arg-type]


def test_candidate_hints_count_only_a_single_blocker() -> None:
    candidate = _person()
    needs = [
        _need(id="k1", must_skills=["kubernetes"]),
        _need(id="k2", must_skills=["kubernetes"]),
        _need(id="salary", must_skills=["go"], salary_to=100_000, salary_from=50_000),
        _need(id="format", must_skills=["go"], formats=["office"]),
        _need(id="both", must_skills=["kubernetes"], salary_to=100_000, salary_from=50_000),
        _need(id="other", specialization="frontend", must_skills=["react"]),
    ]
    hints = build_candidate_hints(candidate, needs, peers=[])
    skill = next(item for item in hints if item["type"] == "skill")
    assert "Kubernetes" in skill["title"]
    assert "+2 компаний" in skill["title"]
    assert "(40 %)" in skill["title"]
    salary = next(item for item in hints if item["id"] == "salary")
    assert salary["title"].startswith("1 компаний отсекают вас по зарплате")
    assert "40 % вилок" in salary["title"]
    form = next(item for item in hints if item["id"] == "format")
    assert form["title"] == "Рассмотрите гибрид — +1 компаний"
    assert len(hints) == 3
    assert hints == sorted(hints, key=lambda item: (-item["priority"], item["id"]))


def test_rank_hint_place_matches_the_rescored_candidate() -> None:
    today = date(2026, 10, 11)
    candidate = _person(last_active_at=datetime(2025, 9, 1, tzinfo=UTC))
    peer = _person(candidate_id="peer", last_active_at=datetime(2026, 10, 11, tzinfo=UTC))
    need = _need(id="pool")
    hints = build_candidate_hints(candidate, [need], [peer], today=today)
    fresh = next(item for item in hints if item["id"] == "rank:fresh")
    assert "2 → 1" in fresh["title"]
    assert fresh["effect_text"] == "2 → 1"
