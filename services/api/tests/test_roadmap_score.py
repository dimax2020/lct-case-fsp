from app.assessment.roadmap_bank import choose_probe_ids, probes_for
from app.assessment.roadmap_score import (
    block_score,
    check_score,
    concrete_score,
    cooldown_for,
    grade_from_latent,
    next_level,
    start_level,
    study_items,
    update_latent,
)


def test_start_level_maps_edges_into_the_band() -> None:
    assert start_level("intern") == "junior"
    assert start_level("junior") == "junior"
    assert start_level("middle") == "middle"
    assert start_level("senior") == "senior"
    assert start_level("lead") == "senior"


def test_strong_block_raises_the_level_and_the_latent() -> None:
    assert check_score(["yes", "yes", "unknown", "no"]) == (1 + 1 + 0.15 + 0) / 4
    assert next_level("middle", 0.8) == "senior"
    assert next_level("senior", 0.9) == "senior"
    assert update_latent(2, 0.9) > 2


def test_weak_block_drops_toward_junior() -> None:
    assert next_level("middle", 0.2) == "junior"
    assert next_level("junior", 0.1) == "junior"
    assert grade_from_latent(0.6, "middle") == "junior"


def test_cooldown_is_shorter_when_the_measured_grade_is_higher() -> None:
    days, outcome = cooldown_for("middle", "senior")
    assert outcome == "up"
    assert days < 90
    slow, dropped = cooldown_for("senior", "junior")
    assert dropped == "down"
    assert slow > 90
    same_days, same = cooldown_for("middle", "middle")
    assert same == "same"
    assert same_days == 90


def test_concrete_answer_needs_two_rubric_hits() -> None:
    assert concrete_score("создан новый ресурс", ("создан", "ресурс", "location")) == 1
    assert concrete_score("не знаю", ("создан", "ресурс")) == 0
    assert block_score(1, 0) < block_score(0, 1)


def test_study_list_keeps_unknowns_and_a_missed_question() -> None:
    items = study_items(
        {"a": "yes", "b": "unknown", "c": "no"},
        [("a", "Знаю GET"), ("b", "Знаю ETag"), ("c", "Знаю CORS")],
        "не помню",
        "Чем 201 отличается от 200?",
        ("создан", "ресурс"),
    )
    assert items == [
        "Знаю ETag. Пока отмечено «не знаю».",
        "Знаю CORS",
        "Разобрать вопрос: Чем 201 отличается от 200?",
    ]
    assert study_items({"a": "yes"}, [("a", "Знаю GET")], "создан новый ресурс", "Вопрос", ("создан", "ресурс")) == []


def test_each_track_samples_three_themes_without_the_whole_map() -> None:
    backend = choose_probe_ids("backend", "same-seed")
    frontend = choose_probe_ids("frontend", "same-seed")
    assert len(backend) == 3
    assert len(frontend) == 3
    assert backend == choose_probe_ids("backend", "same-seed")
    assert len(probes_for("backend")) > 3
    assert len(probes_for("frontend")) > 3
    assert set(backend).isdisjoint(frontend)
