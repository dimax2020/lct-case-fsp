"""Тест рабочего стиля: ключ и подсчёт сверены с примером из бланка HR."""

from app.psych import bank
from app.psych.scoring import (
    candidate_view,
    case_bounds,
    clean_answers,
    disc_pct,
    disc_profile,
    fit_index,
    level_of,
    progress,
    round_half_up,
    scale_bounds,
    scale_pct,
    score,
    statement_bounds,
)


def _full(disc_most: str = "а", disc_least: str = "г", likert: int = 3, case: str = "б") -> dict:
    return {
        "disc": {str(i): {"most": disc_most, "least": disc_least} for i in range(1, 13)},
        "statements": {str(i): likert for i in range(1, 31)},
        "cases": {str(i): case for i in range(1, 6)},
    }


def test_bank_shape_matches_form() -> None:
    assert len(bank.DISC_BLOCKS) == 12
    assert all(len(block) == 4 for block in bank.DISC_BLOCKS)
    assert len(bank.STATEMENTS) == 30
    assert len(bank.CASES) == 5
    # каждая шкала DISC встречается в каждом блоке ровно один раз
    for block in bank.DISC_BLOCKS:
        assert sorted(scale for _, scale in block) == ["C", "D", "I", "S"]
    # каждый пункт части 2 принадлежит ровно одной шкале или социальной желательности, кроме не входящих
    used: list[int] = list(bank.SOCIAL_DESIRABILITY_ITEMS)
    for key in bank.STATEMENT_KEY.values():
        used += key["direct"] + key["reverse"]
    assert len(used) == len(set(used)) == 30


def test_bounds_match_key_table() -> None:
    assert statement_bounds("leadership") == (8, 40)
    assert statement_bounds("teamwork") == (6, 30)
    assert statement_bounds("stress") == (6, 30)
    assert statement_bounds("diligence") == (6, 30)
    assert case_bounds("leadership") == (0, 9)
    assert case_bounds("teamwork") == (1, 6)
    assert case_bounds("stress") == (2, 9)
    assert case_bounds("diligence") == (0, 6)
    assert scale_bounds("leadership") == (8, 49)
    assert scale_bounds("teamwork") == (7, 36)
    assert scale_bounds("stress") == (8, 39)
    assert scale_bounds("diligence") == (6, 36)


def test_disc_percent_table() -> None:
    table = {-12: 0, -9: 13, -6: 25, -3: 38, 0: 50, 3: 63, 6: 75, 9: 88, 12: 100}
    for total, pct in table.items():
        assert disc_pct(total) == pct
    # пример из ключа: D=+6, I=+4, S=−3, C=−7
    assert [disc_pct(v) for v in (6, 4, -3, -7)] == [75, 67, 38, 21]


def test_disc_colour_rules() -> None:
    example = disc_profile({"D": 6, "I": 4, "S": -3, "C": -7})
    assert example["primary"] == ["D"] and example["secondary"] == ["I"]
    assert example["label"] == "Красно-жёлтый"
    assert disc_profile({"D": 2, "I": -2, "S": 1, "C": -1})["balanced"] is True
    tie = disc_profile({"D": 5, "I": 5, "S": -5, "C": -5})
    assert tie["primary"] == ["D", "I"] and tie["secondary"] == []
    far = disc_profile({"D": 9, "I": 4, "S": -6, "C": -7})
    assert far["primary"] == ["D"] and far["secondary"] == []
    negative_second = disc_profile({"D": 6, "I": -1, "S": -2, "C": -3})
    assert negative_second["secondary"] == []


def test_scale_example_from_key() -> None:
    assert scale_pct(39, "leadership") == 76
    assert scale_pct(26, "teamwork") == 66
    assert scale_pct(27, "stress") == 61
    assert scale_pct(33, "diligence") == 90
    percents = {"leadership": 76, "teamwork": 66, "stress": 61, "diligence": 90}
    lead = next(p for p in bank.FIT_PROFILES if p["id"] == "lead")
    analyst = next(p for p in bank.FIT_PROFILES if p["id"] == "analyst")
    assert fit_index(percents, lead["weights"]) == 72
    assert fit_index(percents, analyst["weights"]) == 78
    assert all(sum(p["weights"].values()) == 100 for p in bank.FIT_PROFILES)


def test_levels_and_rounding() -> None:
    assert [level_of(v) for v in (0, 33, 34, 66, 67, 100)] == ["low", "low", "mid", "mid", "high", "high"]
    assert round_half_up(65.5) == 66 and round_half_up(2.5) == 3


def test_full_score_is_consistent() -> None:
    result = score(_full(), duration_seconds=15 * 60)
    assert result["disc_check"] == 0
    by_scale = {item["scale"]: item for item in result["scales"]}
    # все утверждения «3»: прямые и обратные дают по 3 балла
    assert by_scale["leadership"]["statements"] == 24
    # ситуации «б»: Л 0+3+3, К 3+3, С 1+3+0, Т 2+3
    assert by_scale["leadership"]["situations"] == 6
    assert by_scale["teamwork"]["situations"] == 6
    assert by_scale["stress"]["situations"] == 4
    assert by_scale["diligence"]["situations"] == 5
    assert result["social_desirability"] == {"sum": 12, "pct": 50, "flag": False}
    # 30 одинаковых ответов подряд — флаг однотипных ответов
    assert [flag["id"] for flag in result["flags"]] == ["straight_line"]
    assert result["skipped"]["total"] == 0


def test_reverse_items_and_social_flag() -> None:
    answers = _full()
    answers["statements"] = {str(i): (5 if i % 2 else 4) for i in range(1, 31)}
    for item in bank.SOCIAL_DESIRABILITY_ITEMS:
        answers["statements"][str(item)] = 5
    result = score(answers, duration_seconds=12 * 60)
    assert result["social_desirability"]["flag"] is True
    assert result["social_desirability"]["sum"] == 20
    assert "social_desirability" in [flag["id"] for flag in result["flags"]]
    team = next(item for item in result["scales"] if item["scale"] == "teamwork")
    # прямые 3,17,23 → 5; 18 → 4; обратные 1 (ответ 5) → 1, 5 (ответ 5) → 1
    assert team["statements"] == 5 + 5 + 4 + 5 + 1 + 1


def test_skips_imputation_and_flags() -> None:
    answers = _full(likert=4)
    del answers["statements"]["9"]  # лидерство, прямой
    del answers["cases"]["5"]
    answers["disc"].pop("12")
    result = score(answers, duration_seconds=5 * 60)
    lead = next(item for item in result["scales"] if item["scale"] == "leadership")
    # остальные 7 пунктов: 5 прямых по 4 и 2 обратных по 2 → среднее 24/7 замещает пропуск
    assert abs(lead["statements"] - round(24 + 24 / 7, 1)) < 0.11
    assert result["skipped"] == {"disc": 1, "statements": 1, "cases": 1, "total": 3}
    ids = [flag["id"] for flag in result["flags"]]
    assert "too_fast" in ids and "skips" not in ids
    answers["statements"].pop("10")
    assert "skips" in [flag["id"] for flag in score(answers)["flags"]]


def test_clean_answers_drops_garbage() -> None:
    clean = clean_answers({"disc": {"1": {"most": "а", "least": "а"}, "99": {"most": "б"}},
                           "statements": {"1": 7, "2": True, "3": 2}, "cases": {"1": "x", "2": "г"}})
    assert clean["disc"] == {"1": {"most": "а"}}
    assert clean["statements"] == {"3": 2}
    assert clean["cases"] == {"2": "г"}
    assert progress(clean)["blocks_done"] == 0


def test_public_test_has_no_key() -> None:
    public = bank.public_test()
    text = repr(public)
    for secret in ("'D'", "'I'", "'S'", "'C'", "points", "reverse", "weights"):
        assert secret not in text
    assert len(public["blocks"]) == 12 and len(public["statements"]) == 30 and len(public["cases"]) == 5


def test_candidate_view_hides_hr_details() -> None:
    view = candidate_view(score(_full(), duration_seconds=600))
    assert "flags" not in view and "social_desirability" not in view
    assert set(view["scales"][0]) == {"scale", "title", "pct", "level", "level_title", "level_text"}


def test_migration_006_adds_psych_and_privacy() -> None:
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "alembic" / "versions" / "006_psych_privacy.py").read_text(encoding="utf-8")
    assert 'down_revision = "005_roadmap_runs"' in text
    assert "CREATE TABLE IF NOT EXISTS psych_attempts" in text
    for column in ("show_full_name", "show_current_job", "show_fsp", "show_pdf", "show_psych",
                   "consent_processing_at", "consent_publication_at", "website", "logo"):
        assert column in text
