"""Formula boundaries, the must gate, and stable shortlist order. No database."""

from datetime import UTC, date, datetime

import pytest
from app.core.settings import get_settings
from app.matching.config import C_WEIGHTS, E_WEIGHTS, MUST_GATE, SALARY_FLOOR_RATIO, SALARY_FULL_RATIO
from app.matching.formulas import (
    benefits_score,
    cosine,
    domain_fit,
    experience_fit,
    final_s,
    format_fit,
    fresh_score,
    passes_hard_filters,
    process_score,
    recency_factor,
    requirement_coverage,
    salary_fit,
    similarity_from_cosine,
    skill_coverage_value,
    split_ranked,
    stack_interest,
)
from app.matching.service import NeedView, RequirementView, score_pair, shortlist_cache_key
from app.profile.service import CandidateFeatures, EvidenceFeature, FspFeature, SkillFeature


def _need(**overrides: object) -> NeedView:
    data: dict[str, object] = {
        "id": "need-1",
        "specialization": "backend",
        "grades": ["middle"],
        "salary_from": 300_000,
        "salary_to": 400_000,
        "formats": ["remote"],
        "city": "Новосибирск",
        "must_skills": ["go"],
        "nice_skills": [],
        "domain": "fintech",
        "stages": 2,
        "benefits": ["dms", "accreditation", "flexible_start"],
        "requirements": [],
        "description": "x" * 300,
    }
    data.update(overrides)
    return NeedView(**data)  # type: ignore[arg-type]


def _candidate(**overrides: object) -> CandidateFeatures:
    data: dict[str, object] = {
        "candidate_id": "cand-1",
        "full_name": "Алексей Кузнецов",
        "display_name": "Алексей К.",
        "specialization": "backend",
        "grade": "middle",
        "grade_score": 80.0,
        "min_salary": 200_000,
        "formats": ["remote"],
        "status": "seeking",
        "visible": True,
        "city": "Новосибирск",
        "liked_skills": ["go"],
        "disliked_skills": [],
        "liked_domains": ["fintech"],
        "blocked_domains": [],
        "last_active_at": datetime.now(UTC),
        "skills": [SkillFeature(skill_id="go", score=80, source="test")],
        "evidence": [],
        "fsp": [],
        "open_invites": 0,
        "experience_years": 4.0,
    }
    data.update(overrides)
    return CandidateFeatures(**data)  # type: ignore[arg-type]


async def test_score_pair_hand_computed_middle() -> None:
    result = await score_pair(_need(), _candidate())
    # must 0.8*0.30 + grade 1*0.20 + skill 0.8*0.15 + fresh 1*0.05 = 0.61; C = 1
    assert result.e == pytest.approx(0.61)
    assert result.c == pytest.approx(1.0)
    assert result.s == pytest.approx(0.61)
    assert result.gated is False
    assert result.features["must_cov"] == pytest.approx(0.8)
    assert result.features["grade_fit"] == pytest.approx(1.0)
    assert result.features["ef"] == pytest.approx(0.0)
    assert "Тест: Go 80/100" in result.explanations
    assert 1 <= len(result.explanations) <= 3


async def test_score_pair_is_deterministic() -> None:
    need = _need()
    candidate = _candidate()
    assert await score_pair(need, candidate) == await score_pair(need, candidate)


async def test_must_gate_boundaries() -> None:
    below = _candidate(skills=[SkillFeature(skill_id="go", score=29, source="test")])
    exact = _candidate(skills=[SkillFeature(skill_id="go", score=30, source="test")])
    missing = _candidate(skills=[])
    resume_only = _candidate(skills=[SkillFeature(skill_id="go", score=None, source="resume")])
    low_test_and_resume = _candidate(
        skills=[
            SkillFeature(skill_id="go", score=20, source="test"),
            SkillFeature(skill_id="go", score=None, source="resume"),
        ]
    )
    assert (await score_pair(_need(), below)).gated is True
    assert (await score_pair(_need(), exact)).gated is False
    assert (await score_pair(_need(), exact)).features["must_cov"] == pytest.approx(0.3)
    assert (await score_pair(_need(), missing)).gated is True
    assert (await score_pair(_need(), resume_only)).gated is False
    assert (await score_pair(_need(), resume_only)).features["must_cov"] == pytest.approx(0.4)
    assert (await score_pair(_need(), low_test_and_resume)).gated is True
    assert skill_coverage_value([SkillFeature("go", 100, "test")], profile_fsp=True) == pytest.approx(1.0)
    assert skill_coverage_value([SkillFeature("go", None, "fsp_id")], profile_fsp=True) == pytest.approx(0.8)
    assert skill_coverage_value([SkillFeature("go", None, "fsp_id")], profile_fsp=False) == pytest.approx(0.0)
    assert MUST_GATE == pytest.approx(0.3)


async def test_two_must_skills_gate_on_any() -> None:
    need = _need(must_skills=["go", "kafka"])
    one_missing = _candidate(skills=[SkillFeature(skill_id="go", score=100, source="test")])
    result = await score_pair(need, one_missing)
    assert result.gated is True
    assert result.features["must_cov"] == pytest.approx(0.5)
    assert result.coverages["kafka"] == pytest.approx(0.0)


async def test_salary_fit_boundaries() -> None:
    minimum = 100_000
    floor = SALARY_FLOOR_RATIO * minimum
    full = SALARY_FULL_RATIO * minimum
    assert salary_fit(floor, minimum) == pytest.approx(0.0)
    assert salary_fit(floor - 1, minimum) == pytest.approx(0.0)
    assert salary_fit(full, minimum) == pytest.approx(1.0)
    assert salary_fit(full + 1, minimum) == pytest.approx(1.0)
    assert salary_fit(90_000, minimum) == pytest.approx(0.0)
    assert salary_fit(115_000, minimum) == pytest.approx(1.0)
    midpoint = floor + 0.5 * (full - floor)
    assert salary_fit(midpoint, minimum) == pytest.approx(0.5)
    assert salary_fit(400_000, None) == pytest.approx(1.0)


async def test_format_domain_stack_process_benefits() -> None:
    assert format_fit(["remote"], ["remote"]) == pytest.approx(1.0)
    assert format_fit(["hybrid"], ["remote"]) == pytest.approx(0.5)
    assert format_fit(["office"], ["remote"]) == pytest.approx(0.0)
    assert format_fit(["hybrid", "remote"], ["remote"]) == pytest.approx(1.0)
    need = _need(must_skills=["go", "kafka"], nice_skills=["postgresql"])
    full = _candidate(liked_skills=["go", "kafka", "postgresql"], disliked_skills=[])
    assert stack_interest(need, full) == pytest.approx(1.0)
    penalized = _candidate(liked_skills=["go", "kafka", "postgresql"], disliked_skills=["kafka", "go", "postgresql"])
    assert stack_interest(need, penalized) == pytest.approx(0.0)
    assert domain_fit(_need(), _candidate()) == pytest.approx(1.0)
    assert domain_fit(_need(), _candidate(liked_domains=[])) == pytest.approx(0.5)
    assert domain_fit(_need(), _candidate(blocked_domains=["fintech"])) == pytest.approx(0.0)
    assert benefits_score(["dms", "accreditation", "flexible_start"]) == pytest.approx(1.0)
    assert benefits_score(["dms"]) == pytest.approx(1 / 3)
    assert benefits_score([]) == pytest.approx(0.0)
    assert process_score(2) == pytest.approx(1.0)
    assert process_score(1) == pytest.approx(1.0)
    assert process_score(3) == pytest.approx(0.5)
    assert process_score(4) == pytest.approx(0.0)


async def test_senior_c_weights_shrink_the_rest() -> None:
    poor_salary = _need(grades=["middle"], salary_from=0, salary_to=90_000)
    candidate = _candidate(min_salary=100_000)
    middle = await score_pair(poor_salary, candidate)
    senior = await score_pair(_need(grades=["senior"], salary_from=0, salary_to=90_000), candidate)
    assert salary_fit(90_000, 100_000) == pytest.approx(0.0)
    assert middle.c == pytest.approx(sum(weight for name, weight in C_WEIGHTS["default"].items() if name != "salary_fit"))
    assert senior.c == pytest.approx(sum(weight for name, weight in C_WEIGHTS["senior"].items() if name != "salary_fit"))


def test_e_weights_sum_and_all_ones() -> None:
    from app.matching.formulas import weighted_sum

    ones = {name: 1.0 for name in E_WEIGHTS["middle"]}
    assert weighted_sum(ones, E_WEIGHTS["middle"]) == pytest.approx(1.0)
    assert weighted_sum({name: 0.0 for name in ones}, E_WEIGHTS["senior"]) == pytest.approx(0.0)


def test_fresh_and_recency_boundaries() -> None:
    today = date(2026, 10, 11)
    assert fresh_score(datetime(2026, 10, 11, tzinfo=UTC), today) == pytest.approx(1.0)
    assert fresh_score(datetime(2026, 8, 12, tzinfo=UTC), today) == pytest.approx(2.718281828 ** -1, rel=1e-3)
    assert fresh_score(None, today) == pytest.approx(0.0)
    assert recency_factor(0) == pytest.approx(1.0)
    assert recency_factor(2) == pytest.approx(0.5)
    assert recency_factor(4) == pytest.approx(0.25)
    assert recency_factor(None) == pytest.approx(1.0)


def test_similarity_clip_and_noisy_or() -> None:
    assert similarity_from_cosine(0.75) == pytest.approx(0.0)
    assert similarity_from_cosine(0.90) == pytest.approx(1.0)
    assert similarity_from_cosine(0.825) == pytest.approx(0.5)
    assert similarity_from_cosine(0.5) == pytest.approx(0.0)
    assert similarity_from_cosine(1.0) == pytest.approx(1.0)
    assert requirement_coverage([]) == pytest.approx(0.0)
    assert requirement_coverage([1.0]) == pytest.approx(1.0)
    assert requirement_coverage([0.5, 0.5, 0.0]) == pytest.approx(0.75)
    assert requirement_coverage([0.2, 0.2, 0.2]) == pytest.approx(1 - 0.8**3)
    left = [1.0, 0.0]
    right = [0.825, (1 - 0.825**2) ** 0.5]
    assert cosine(left, right) == pytest.approx(0.825)
    assert cosine([0.0, 0.0], [1.0, 0.0]) is None


def test_experience_fit_noisy_or_and_nearest_three() -> None:
    today = date(2026, 10, 11)
    requirement = RequirementView(
        id="r1",
        task="поток событий",
        domain="fintech",
        skills=["kafka"],
        scale=None,
        kind="must",
        embedding=[1.0, 0.0],
    )
    def evidence(evidence_id: str, embedding: list[float], trust: float = 1.0) -> EvidenceFeature:
        return EvidenceFeature(
            id=evidence_id,
            task=evidence_id,
            domain="fintech",
            skills=["kafka"],
            role="owner",
            date=today,
            trust=trust,
            embedding=embedding,
            origin="project",
            evidence_span=evidence_id,
        )

    perfect = _candidate(evidence=[evidence("e1", [1.0, 0.0])])
    fit, pairs = experience_fit(_need(requirements=[requirement]), perfect, today)
    assert fit == pytest.approx(1.0)
    assert pairs[0].score == pytest.approx(1.0)
    assert "поток событий" in pairs[0].text

    orthogonal = [0.0, 1.0]
    near = [
        evidence("near-1", [1.0, 0.0], trust=0.0),
        evidence("near-2", [0.96, (1 - 0.96**2) ** 0.5], trust=0.0),
        evidence("near-3", [0.9, (1 - 0.9**2) ** 0.5], trust=0.0),
        evidence("far", orthogonal, trust=1.0),
    ]
    fit_far, pairs_far = experience_fit(_need(requirements=[requirement]), _candidate(evidence=near), today)
    assert fit_far == pytest.approx(0.0)
    assert pairs_far[0].evidence_id != "far"

    empty = experience_fit(_need(requirements=[]), perfect, today)
    assert empty == (0.0, [])
    zeros = RequirementView("r0", "задача", None, [], None, "must", [0.0, 0.0])
    assert experience_fit(_need(requirements=[zeros]), perfect, today)[0] == pytest.approx(0.0)


def test_final_s_open_invites(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "match_alpha", 1.0)
    monkeypatch.setattr(settings, "match_beta", 0.15)
    assert final_s(0.61, 1.0, 0, 1.0, 0.15) == pytest.approx(0.61)
    assert final_s(0.61, 1.0, 2, 1.0, 0.15) == pytest.approx(0.61 / 1.3)
    assert final_s(0.5, 0.0, 0, 1.0, 0.15) == pytest.approx(0.0)
    monkeypatch.setattr(settings, "match_alpha", 2.0)
    monkeypatch.setattr(settings, "match_beta", 0.5)
    assert final_s(0.8, 0.5, 2, 2.0, 0.5) == pytest.approx(0.8 * 0.25 / 2)


async def test_settings_alpha_beta_change_s(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "match_alpha", 2.0)
    monkeypatch.setattr(settings, "match_beta", 0.5)
    result = await score_pair(_need(), _candidate(open_invites=2))
    assert result.s == pytest.approx(result.e * (result.c**2) / 2.0)


def test_hard_filters_match_section_6_1() -> None:
    allowed = {"backend", "devops", "frontend"}
    need = _need()
    assert passes_hard_filters(need, _candidate(), allowed)
    assert passes_hard_filters(need, _candidate(status="open"), allowed)
    assert passes_hard_filters(need, _candidate(specialization="devops"), allowed)
    assert not passes_hard_filters(need, _candidate(specialization="data_ml"), allowed)
    assert passes_hard_filters(need, _candidate(grade="junior"), allowed)
    assert passes_hard_filters(need, _candidate(grade="senior"), allowed)
    assert not passes_hard_filters(need, _candidate(grade="lead"), allowed)
    assert not passes_hard_filters(need, _candidate(status="paused"), allowed)
    assert not passes_hard_filters(need, _candidate(visible=False), allowed)
    assert not passes_hard_filters(need, _candidate(blocked_domains=["fintech"]), allowed)
    tight = _need(salary_to=90_000, salary_from=0)
    assert passes_hard_filters(tight, _candidate(min_salary=100_000), allowed)
    assert not passes_hard_filters(_need(salary_to=89_999, salary_from=0), _candidate(min_salary=100_000), allowed)
    assert passes_hard_filters(_need(formats=["hybrid"]), _candidate(formats=["remote"]), allowed)
    assert not passes_hard_filters(_need(formats=["office"]), _candidate(formats=["remote"]), allowed)


def test_split_ranked_is_stable_and_hides_the_gate() -> None:
    main, hidden = split_ranked(
        [
            ("b", 0.5, False),
            ("a", 0.5, False),
            ("c", 0.9, False),
            ("d", 1.0, True),
        ]
    )
    assert main == ["c", "a", "b"]
    assert hidden == ["d"]
    again, _ = split_ranked([("b", 0.5, False), ("a", 0.5, False), ("c", 0.9, False)])
    assert again == main


def test_shortlist_cache_key_is_the_need_id() -> None:
    from uuid import UUID

    need_id = UUID("11111111-1111-1111-1111-111111111111")
    assert shortlist_cache_key(need_id) == "11111111-1111-1111-1111-111111111111"


async def test_fsp_profile_versus_other_discipline() -> None:
    profile = _candidate(fsp=[FspFeature(discipline="backend", event="Чемпионат", place=2, year=2025)], skills=[])
    other = _candidate(fsp=[FspFeature(discipline="robot", event="Кубок", place=1, year=2024)], skills=[])
    none = _candidate(fsp=[], skills=[])
    assert (await score_pair(_need(must_skills=["go"]), profile)).features["fsp"] == pytest.approx(1.0)
    assert (await score_pair(_need(), other)).features["fsp"] == pytest.approx(0.5)
    assert (await score_pair(_need(), none)).features["fsp"] == pytest.approx(0.0)
    assert (await score_pair(_need(), _candidate(last_active_at=None))).features["fresh"] == pytest.approx(0.0)
