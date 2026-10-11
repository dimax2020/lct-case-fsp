from datetime import UTC, date, datetime
from uuid import uuid4

from app.matching.formulas import score_breakdown
from app.profile.daily import HINT, boost_active, boost_until_for, pick_skill, prompt_for
from app.profile.service import CandidateFeatures, SkillFeature

from test_matching import _candidate, _need


def test_prompt_is_a_best_experience_question() -> None:
    assert prompt_for("Redis") == "Опиши свой лучший опыт использования Redis."
    assert "профиле" in HINT and "следующий день" in HINT


def test_skill_rotates_by_day_and_skips_used() -> None:
    candidate = uuid4()
    first, _ = pick_skill(candidate, date(2026, 10, 11), ["redis", "kafka"], set())
    second, _ = pick_skill(candidate, date(2026, 10, 12), ["redis", "kafka"], {first})
    assert first in {"redis", "kafka"}
    assert second in {"redis", "kafka"}
    assert first != second


def test_boost_covers_today_and_the_next_calendar_day() -> None:
    until = boost_until_for(date(2026, 10, 11))
    assert until == datetime(2026, 10, 13, tzinfo=UTC)
    assert boost_active(until, date(2026, 10, 11)) is True
    assert boost_active(until, date(2026, 10, 12)) is True
    assert boost_active(until, date(2026, 10, 13)) is False


def test_daily_boost_raises_shortlist_score() -> None:
    today = date(2026, 10, 12)
    stale = datetime(2025, 1, 1, tzinfo=UTC)
    plain = score_breakdown(_need(), _candidate(last_active_at=stale), today)
    boosted = score_breakdown(
        _need(),
        _candidate(last_active_at=stale, daily_boost_until=datetime(2026, 10, 13, tzinfo=UTC)),
        today,
    )
    assert plain.features["daily_boost"] == 0
    assert boosted.features["daily_boost"] == 1
    assert boosted.features["fresh"] == 1
    assert boosted.e > plain.e
    assert any("буст" in line.lower() for line in boosted.explanations)


def test_candidate_features_keep_boost_optional() -> None:
    person = CandidateFeatures(
        candidate_id="x",
        full_name="A",
        display_name="A",
        specialization="backend",
        grade="middle",
        grade_score=80,
        min_salary=1,
        formats=["remote"],
        status="seeking",
        visible=True,
        city=None,
        liked_skills=[],
        disliked_skills=[],
        liked_domains=[],
        blocked_domains=[],
        last_active_at=None,
        skills=[SkillFeature(skill_id="go", score=80, source="test")],
    )
    assert person.daily_boost_until is None


def test_same_day_pick_is_stable() -> None:
    candidate = uuid4()
    day = date(2026, 10, 11)
    assert pick_skill(candidate, day, ["redis"], set()) == pick_skill(candidate, day, ["redis"], set())
