"""Relevance labels for the gold set. Independent of the matching formula.

The rules are the source of truth for eval/gold.jsonl and are restated in eval/RUBRIC.md.
"""

from __future__ import annotations

import re

GRADES = ("intern", "junior", "middle", "senior", "lead")


def grade_distance(left: str, right: str) -> int | None:
    try:
        return abs(GRADES.index(left) - GRADES.index(right))
    except ValueError:
        return None


def nearest_grade_distance(candidate_grade: str | None, need_grades: list[str]) -> int | None:
    if not candidate_grade or not need_grades:
        return None
    distances = [grade_distance(candidate_grade, grade) for grade in need_grades]
    if any(item is None for item in distances):
        return None
    return min(item for item in distances if item is not None)


def skill_ids(candidate: dict) -> set[str]:
    return {row["skill_id"] for row in candidate.get("skills", [])}


def has_confirmed_must(candidate: dict, must: list[str]) -> bool:
    for row in candidate.get("skills", []):
        if row["skill_id"] not in must or row.get("source") != "test":
            continue
        score = row.get("score")
        if score is not None and score >= 70:
            return True
    return False


def _text_covers_skill(text: str, skill_id: str, skill_names: dict[str, list[str]]) -> bool:
    folded = text.casefold().replace("ё", "е")
    for alias in skill_names.get(skill_id, [skill_id]):
        needle = re.escape(alias.casefold().replace("ё", "е"))
        if re.search(rf"(?<![0-9a-zа-яё]){needle}(?![0-9a-zа-яё])", folded):
            return True
    return False


def has_task_evidence(candidate: dict, must: list[str], skill_names: dict[str, list[str]]) -> bool:
    for project in candidate.get("projects", []):
        if len(project.get("task", "")) < 80:
            continue
        if set(project.get("skills", [])) & set(must):
            return True
        if any(_text_covers_skill(project.get("task", ""), skill, skill_names) for skill in must):
            return True
    for experience in candidate.get("experiences", []):
        description = experience.get("description", "")
        if len(description) < 80:
            continue
        if any(_text_covers_skill(description, skill, skill_names) for skill in must):
            return True
    return False


def relevance(candidate: dict, need: dict, adjacent: dict[str, set[str]], skill_names: dict[str, list[str]]) -> int:
    """Return 3, 2, 1 or 0. Higher levels are checked first so a 3 is not also a 1."""
    spec = candidate.get("specialization")
    need_spec = need["specialization"]
    spec_match = spec == need_spec
    spec_adjacent = spec in adjacent.get(need_spec, set())
    must = list(need.get("must_skills", []))
    nice = list(need.get("nice_skills", []))
    owned = skill_ids(candidate)
    must_hits = [skill for skill in must if skill in owned]
    distance = nearest_grade_distance(candidate.get("grade"), list(need.get("grades", [])))
    salary = candidate.get("min_salary")
    salary_to = need["salary_to"]
    salary_ok = salary is None or salary <= salary_to
    salary_soft = salary is None or salary <= int(salary_to * 1.3)
    formats_ok = bool(set(candidate.get("formats", [])) & set(need.get("formats", [])))
    domain = need.get("domain")
    domain_ok = domain not in set(candidate.get("blocked_domains", []))
    status_ok = candidate.get("status") in {"seeking", "open"} and bool(candidate.get("visible"))
    half = len(must_hits) * 2 >= len(must) if must else False
    close = distance is not None and distance <= 1

    level3 = (
        spec_match
        and close
        and must
        and len(must_hits) == len(must)
        and has_confirmed_must(candidate, must)
        and salary_ok
        and formats_ok
        and domain_ok
        and status_ok
        and has_task_evidence(candidate, must, skill_names)
    )
    if level3:
        return 3
    level2 = spec_match or spec_adjacent
    level2 = level2 and close and half and salary_soft and status_ok and domain_ok
    if level2:
        return 2
    shares_skill = bool(set(must + nice) & owned)
    if shares_skill or spec_match or spec_adjacent:
        return 1
    return 0
