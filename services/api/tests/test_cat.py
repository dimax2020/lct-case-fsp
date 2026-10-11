import re
from collections import Counter

import numpy as np
from app.assessment.blueprint import build_blueprint
from app.assessment.cat_engine import decide_grade, eap, grade_from_theta, select_item, should_stop, start_theta, theta_to_score
from app.assessment.item_bank import _SKILL_GROUPS, all_items, items_for, overlap, score_response, skills_of


def test_grade_cuts_follow_bank() -> None:
    assert grade_from_theta(-2.0) == "intern"
    assert grade_from_theta(-1.2) == "junior"
    assert grade_from_theta(0.0) == "junior"
    assert grade_from_theta(0.2) == "middle"
    assert grade_from_theta(1.2) == "senior"
    assert grade_from_theta(2.3) == "lead"


def test_first_assignment_uses_measured_grade() -> None:
    decision = decide_grade(0.5, 0.2, "junior", None)
    assert decision.assigned == "middle"
    assert decision.measured == "middle"
    assert decision.decision == "above"


def test_no_forced_downgrade() -> None:
    decision = decide_grade(-1.5, 0.2, "senior", "senior")
    assert decision.assigned == "senior"
    assert decision.measured == "intern"
    assert decision.decision == "below"
    assert decision.ready_for_next is False


def test_retake_assigns_declared() -> None:
    decision = decide_grade(-1.0, 0.2, "junior", "middle", grade_change=True)
    assert decision.assigned == "junior"
    failed_up = decide_grade(0.0, 0.6, "senior", "middle", grade_change=True)
    assert failed_up.assigned == "middle"


def test_eap_moves_with_correct_answers() -> None:
    start, _ = eap([])
    after, se = eap([(1.2, -1.6, 1.0), (1.0, -1.0, 1.0), (1.3, -0.8, 1.0)])
    assert after > start
    assert se < 2.0


def test_stop_rule() -> None:
    assert should_stop(7, 0.1) is False
    assert should_stop(8, 0.29) is True
    assert should_stop(8, 0.31) is False


def test_selection_avoids_used_and_respects_exposure() -> None:
    a = np.ones(6)
    b = np.linspace(-2, 2, 6)
    shown = np.array([80, 80, 80, 1, 1, 1], dtype=float)
    rng = np.random.default_rng(1)
    picked = select_item(0.0, a, b, shown, tests=200, used=[3], rng=rng)
    assert picked is not None
    assert picked.index not in {0, 1, 2, 3}


def test_bank_has_playable_items_per_spec() -> None:
    assert {item.specialization for item in all_items()} == {"backend", "frontend"}
    assert items_for("devops") == ()
    assert items_for("data_ml") == ()
    for spec in ("backend", "frontend"):
        pool = items_for(spec)
        assert len(pool) >= 30
        for item in pool:
            assert item.body.strip()
            assert not re.search(r"(?<![=$])\{[a-z_]+\}", item.body), item.id
            answerable = bool(item.options and item.correct) or bool(item.accept) or bool(item.keys)
            assert answerable, item.id
            if item.options:
                assert len(item.options) >= 2
                assert set(item.correct) <= {row["id"] for row in item.options}


def test_skill_scores_use_coarse_taxonomy_skills() -> None:
    for spec in ("backend", "frontend"):
        pool = items_for(spec)
        groups = _SKILL_GROUPS[spec]
        unmapped = {tag for item in pool for tag in item.tags} - {tag for tags in groups.values() for tag in tags}
        assert not unmapped, unmapped
        counts = Counter(skill for item in pool for skill in skills_of(item))
        assert set(counts) == set(groups)
        assert len(counts) <= 10
        assert sum(n >= 2 for n in counts.values()) >= len(counts) - 2, counts


def _item(task_id: str):
    item = next(row for spec in ("backend", "frontend") for row in items_for(spec) if row.id == task_id)
    return item


def test_choice_scoring() -> None:
    single = _item("BE-J-01")
    assert score_response(single, answer="b", code=None, skipped=False) == 1.0
    assert score_response(single, answer="a", code=None, skipped=False) == 0.0
    multi = _item("BE-J-05")
    assert multi.multiple
    assert score_response(multi, answer="a,d", code=None, skipped=False) == 1.0
    assert score_response(multi, answer="a", code=None, skipped=False) == 0.5
    assert score_response(multi, answer="a,b,c,d", code=None, skipped=False) == 0.0


def test_short_and_rubric_scoring() -> None:
    assert score_response(_item("BE-J-03"), answer="3 строки", code=None, skipped=False) == 1.0
    assert score_response(_item("BE-J-03"), answer="5", code=None, skipped=False) == 0.0
    assert score_response(_item("FE-M-01"), answer="A, D, F, C, E, B", code=None, skipped=False) == 1.0
    sql = _item("BE-J-06")
    good = (
        "SELECT c.name, SUM(o.amount) t FROM customers c JOIN orders o ON o.customer_id = c.id "
        "GROUP BY c.name HAVING SUM(o.amount) > 10000 ORDER BY t DESC"
    )
    assert score_response(sql, answer=None, code=good, skipped=False) == 1.0
    assert score_response(sql, answer=None, code="SELECT * FROM customers", skipped=False) < 0.75
    assert overlap("git reset --soft HEAD~1", "git reset --soft HEAD~1 и mixed") > 0.4


def test_blueprint_prefers_matching_tags() -> None:
    plan = build_blueprint("backend", "middle", ["postgresql", "kafka"], "платежи идемпотентность транзакции")
    assert plan.sample
    assert plan.theory + plan.practice + plan.debug + plan.case == 100
    assert theta_to_score(start_theta("middle")) > 20
