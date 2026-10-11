import numpy as np
from app.assessment.blueprint import build_blueprint
from app.assessment.cat_engine import decide_grade, eap, grade_from_theta, select_item, should_stop, start_theta, theta_to_score
from app.assessment.item_bank import all_items, items_for, overlap, score_response


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
    assert len(all_items()) >= 200
    for spec in ("backend", "frontend", "devops", "data_ml"):
        pool = items_for(spec)
        assert len(pool) >= 60
        assert any(item.source == "detailed" for item in pool)
        assert all(item.body.strip() for item in pool)


def test_mcq_and_text_scoring() -> None:
    item = next(row for row in items_for("backend") if row.id == "BE-J-01")
    assert item.options
    assert score_response(item, answer=item.correct[0], code=None, skipped=False) == 1.0
    assert score_response(item, answer="zzz", code=None, skipped=False) == 0.0
    assert overlap("git reset --soft HEAD~1", "git reset --soft HEAD~1 и mixed") > 0.4


def test_blueprint_prefers_matching_tags() -> None:
    plan = build_blueprint("backend", "middle", ["postgresql", "kafka"], "платежи идемпотентность транзакции")
    assert plan.sample
    assert plan.theory + plan.practice + plan.debug + plan.case == 100
    assert theta_to_score(start_theta("middle")) > 20
