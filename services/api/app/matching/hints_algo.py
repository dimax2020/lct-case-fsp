"""§7 hint selection. Thresholds come from matching.config; this module stays inside matching."""

import copy
from datetime import UTC, date, datetime
from typing import Any

from app.matching.config import (
    EMPLOYER_HINT_MIN_POOL,
    HINT_ACTIVE_DAYS,
    HINT_EFFORT,
    HINT_NEED_SAMPLE,
    HINT_PEER_CAP,
    HINT_TOP,
    MUST_GATE,
)
from app.matching.formulas import (
    format_compatible,
    grade_passes,
    salary_passes,
    score_breakdown,
    skill_coverages,
)
from app.matching.service import NeedView
from app.profile.service import CandidateFeatures, EvidenceFeature, FspFeature, SkillFeature


def _label(skill_id: str) -> str:
    if not skill_id:
        return skill_id
    return skill_id[:1].upper() + skill_id[1:]


def _today() -> date:
    return datetime.now(UTC).date()


def _money(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def average_match(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    return int(round(sum(int(row["match"]) for row in rows) / len(rows)))


def main_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in payload.get("rows") or [] if row.get("bucket") == "main"]


def _active_within(raw: str | None, days: int, today: date) -> bool:
    if not raw:
        return False
    try:
        moment = date.fromisoformat(str(raw)[:10])
    except ValueError:
        return False
    return (today - moment).days <= days


def _narrow_keep(row: dict[str, Any], filt: dict[str, Any], today: date) -> bool:
    if "tested_skill" in filt:
        return str(filt["tested_skill"]) in set(row.get("tested_skills") or [])
    if filt.get("domain_experience"):
        return bool(row.get("domain_hit"))
    if filt.get("active_14d"):
        return _active_within(row.get("last_active_at"), HINT_ACTIVE_DAYS, today)
    if filt.get("has_fsp"):
        return bool(row.get("fsp_disciplines"))
    return True


def apply_employer_hint(payload: dict[str, Any], hint: dict[str, Any], today: date | None = None) -> list[dict[str, Any]]:
    moment = today or _today()
    spec = hint.get("apply") or {}
    kind = spec.get("kind")
    filt = spec.get("filter") or {}
    rows = main_rows(payload)
    if kind == "narrow":
        return [row for row in rows if _narrow_keep(row, filt, moment)]
    if kind == "expand":
        skill = filt.get("drop_must")
        extra = [row for row in payload.get("rows") or [] if row.get("bucket") == f"expand:{skill}"]
        return rows + extra
    if kind == "salary":
        extra = [row for row in payload.get("rows") or [] if row.get("bucket") == "salary"]
        return rows + extra
    return rows


def _narrow_hint(
    payload: dict[str, Any],
    hint_id: str,
    title_prefix: str,
    filt: dict[str, Any],
    today: date,
) -> dict[str, Any] | None:
    rows = main_rows(payload)
    kept = [row for row in rows if _narrow_keep(row, filt, today)]
    before = len(rows)
    after = len(kept)
    if after < EMPLOYER_HINT_MIN_POOL or after >= before:
        return None
    avg_before = average_match(rows)
    avg_after = average_match(kept)
    if avg_after <= avg_before:
        return None
    return {
        "id": hint_id,
        "type": "narrow",
        "title": f"{title_prefix}: {before} → {after}, соответствие {avg_before} % → {avg_after} %",
        "before": before,
        "after": after,
        "avg_before": float(avg_before),
        "avg_after": float(avg_after),
        "apply": {"kind": "narrow", "filter": filt, "patch": None},
        "_priority": float(avg_after - avg_before),
    }


def _expand_hints(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = main_rows(payload)
    before = len(rows)
    found: list[dict[str, Any]] = []
    skills = [str(skill) for skill in payload.get("must_skills") or []]
    for skill in skills:
        extra = [row for row in payload.get("rows") or [] if row.get("bucket") == f"expand:{skill}"]
        gain = len(extra)
        if gain <= 0:
            continue
        after = before + gain
        found.append(
            {
                "id": f"expand:{skill}",
                "type": "expand",
                "title": f"Уберите обязательный {_label(skill)}: +{gain} кандидатов",
                "before": before,
                "after": after,
                "avg_before": None,
                "avg_after": None,
                "apply": {"kind": "expand", "filter": {"drop_must": skill}, "patch": None},
                "_priority": float(gain),
            }
        )
    return found


def _salary_hint(payload: dict[str, Any]) -> dict[str, Any] | None:
    median = payload.get("salary_median")
    if not isinstance(median, int):
        return None
    extra = [row for row in payload.get("rows") or [] if row.get("bucket") == "salary"]
    gain = len(extra)
    if gain <= 0:
        return None
    before = len(main_rows(payload))
    return {
        "id": "salary",
        "type": "salary",
        "title": f"Вилка ниже медианы ожиданий: до {_money(median)} ₽ — +{gain} кандидатов",
        "before": before,
        "after": before + gain,
        "avg_before": None,
        "avg_after": None,
        "apply": {"kind": "salary", "filter": None, "patch": {"salary_to": median}},
        "_priority": float(gain),
    }


_TEXT_TITLES = {
    "scale": "Опишите масштаб задач — точность подборки вырастет",
    "tasks": "Опишите задачи команды — точность подборки вырастет",
    "stack": "Укажите стек в описании — точность подборки вырастет",
    "first_months": "Опишите первые 3 месяца — точность подборки вырастет",
}


def text_gaps(description: str, requirements: list[Any]) -> list[str]:
    text = (description or "").lower()

    def task_of(item: Any) -> str:
        if isinstance(item, dict):
            return str(item.get("task") or "")
        return str(getattr(item, "task", "") or "")

    def scale_of(item: Any) -> str:
        if isinstance(item, dict):
            return str(item.get("scale") or "")
        return str(getattr(item, "scale", "") or "")

    def skills_of(item: Any) -> list[Any]:
        if isinstance(item, dict):
            return list(item.get("skills") or [])
        return list(getattr(item, "skills", []) or [])

    gaps: list[str] = []
    has_task = any(task_of(item).strip() for item in requirements) or "задач" in text
    has_scale = any(scale_of(item).strip() for item in requirements) or any(
        token in text for token in ("масштаб", "нагруз", "rps", "qps", "пользовател")
    )
    has_stack = any(skills_of(item) for item in requirements) or "стек" in text
    has_first = any(token in text for token in ("3 месяц", "три месяц", "первые 3", "первые три", "90 дн"))
    if not has_scale:
        gaps.append("scale")
    if not has_task:
        gaps.append("tasks")
    if not has_stack:
        gaps.append("stack")
    if not has_first:
        gaps.append("first_months")
    return gaps


def _text_hint(payload: dict[str, Any]) -> dict[str, Any] | None:
    gaps = [str(item) for item in payload.get("text_gaps") or []]
    for gap in gaps:
        title = _TEXT_TITLES.get(gap)
        if title is None:
            continue
        return {
            "id": f"text:{gap}",
            "type": "text",
            "title": title,
            "before": None,
            "after": None,
            "avg_before": None,
            "avg_after": None,
            "apply": None,
            "_priority": 0.5,
        }
    return None


def _select_top(hints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for hint in sorted(hints, key=lambda item: (-float(item["_priority"]), str(item["id"]))):
        best.setdefault(str(hint["type"]), hint)
    ordered = sorted(best.values(), key=lambda item: (-float(item["_priority"]), str(item["id"])))
    public: list[dict[str, Any]] = []
    for hint in ordered[:HINT_TOP]:
        public.append({key: value for key, value in hint.items() if key != "_priority"})
    return public


def build_employer_hints(payload: dict[str, Any], today: date | None = None) -> list[dict[str, Any]]:
    moment = today or _today()
    hints: list[dict[str, Any]] = []
    for skill in [str(item) for item in payload.get("must_skills") or []]:
        hint = _narrow_hint(
            payload,
            f"narrow:tested:{skill}",
            f"{_label(skill)} только подтверждённая",
            {"tested_skill": skill},
            moment,
        )
        if hint is not None:
            hints.append(hint)
    domain = payload.get("domain")
    if domain:
        hint = _narrow_hint(
            payload,
            "narrow:domain",
            f"Опыт в домене {domain}",
            {"domain_experience": True},
            moment,
        )
        if hint is not None:
            hints.append(hint)
    active = _narrow_hint(
        payload,
        "narrow:active",
        f"Активен {HINT_ACTIVE_DAYS} дней",
        {"active_14d": True},
        moment,
    )
    if active is not None:
        hints.append(active)
    fsp_hint = _narrow_hint(payload, "narrow:fsp", "Есть достижение ФСП", {"has_fsp": True}, moment)
    if fsp_hint is not None:
        hints.append(fsp_hint)
    hints.extend(_expand_hints(payload))
    salary = _salary_hint(payload)
    if salary is not None:
        hints.append(salary)
    text_hint = _text_hint(payload)
    if text_hint is not None:
        hints.append(text_hint)
    return _select_top(hints)


def _condition_failures(need: NeedView, candidate: CandidateFeatures) -> list[tuple[str, str | None]] | None:
    """None when the need is outside the candidate's specialization or a blocked domain."""
    if candidate.specialization and need.specialization != candidate.specialization:
        return None
    if need.domain and need.domain in set(candidate.blocked_domains):
        return None
    failures: list[tuple[str, str | None]] = []
    coverages = skill_coverages(need, candidate, list(need.must_skills))
    failing = [skill for skill, value in coverages.items() if value < MUST_GATE]
    if len(failing) == 1:
        failures.append(("skill", failing[0]))
    elif len(failing) > 1:
        failures.append(("skill-many", None))
    if not salary_passes(need.salary_to, candidate.min_salary):
        failures.append(("salary", None))
    if not format_compatible(need.formats, candidate.formats):
        failures.append(("format", None))
    if not grade_passes(need.grades, candidate.grade):
        failures.append(("grade", None))
    return failures


def _single_block(need: NeedView, candidate: CandidateFeatures) -> tuple[str, str | None] | None:
    failures = _condition_failures(need, candidate)
    if not failures or len(failures) != 1 or failures[0][0] == "skill-many":
        return None
    return failures[0]


def _in_pool(need: NeedView, candidate: CandidateFeatures) -> bool:
    return _condition_failures(need, candidate) == []


def _median_place(places: list[int]) -> int:
    ordered = sorted(places)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[middle]
    return ordered[middle - 1]


def _place(score: float, others: list[float]) -> int:
    return 1 + sum(1 for other in others if other > score)


def _hint(
    hint_id: str,
    hint_type: str,
    title: str,
    effect_text: str,
    action_label: str,
    action_href: str,
    priority: float,
) -> dict[str, Any]:
    return {
        "id": hint_id,
        "type": hint_type,
        "title": title,
        "effect_text": effect_text,
        "action_label": action_label,
        "action_href": action_href,
        "priority": priority,
    }


def _blocker_hints(candidate: CandidateFeatures, needs: list[NeedView]) -> list[dict[str, Any]]:
    if not needs:
        return []
    grouped: dict[tuple[str, str | None], int] = {}
    for need in needs:
        block = _single_block(need, candidate)
        if block is None:
            continue
        grouped[block] = grouped.get(block, 0) + 1
    total = len(needs)
    hints: list[dict[str, Any]] = []
    for (kind, skill), count in grouped.items():
        share = int(round(100 * count / total))
        if kind == "skill" and skill:
            effort = HINT_EFFORT["mini_test"]
            hints.append(
                _hint(
                    f"skill:{skill}",
                    "skill",
                    f"Подтвердите {_label(skill)} — +{count} компаний ({share} %). Мини-тест 10 мин",
                    f"+{count} компаний ({share} %)",
                    "Мини-тест 10 мин",
                    "/candidate/test",
                    count / effort,
                )
            )
        elif kind == "salary" and candidate.min_salary is not None:
            above = sum(1 for need in needs if candidate.min_salary > need.salary_to)
            percent = int(round(100 * above / total))
            effort = HINT_EFFORT["conditions"]
            hints.append(
                _hint(
                    "salary",
                    "salary",
                    f"{count} компаний отсекают вас по зарплате: ваш минимум выше {percent} % вилок",
                    f"+{count} компаний",
                    "Изменить условия",
                    "/candidate/profile/edit#search",
                    count / effort,
                )
            )
        elif kind == "format":
            effort = HINT_EFFORT["conditions"]
            hints.append(
                _hint(
                    "format",
                    "format",
                    f"Рассмотрите гибрид — +{count} компаний",
                    f"+{count} компаний",
                    "Изменить формат",
                    "/candidate/profile/edit#search",
                    count / effort,
                )
            )
        elif kind == "grade":
            effort = HINT_EFFORT["mini_test"]
            hints.append(
                _hint(
                    "grade",
                    "grade",
                    f"Грейд не совпадает с {count} компаниями ({share} %). Пройдите тест",
                    f"+{count} компаний ({share} %)",
                    "Пройти тест",
                    "/candidate/test",
                    count / effort,
                )
            )
    return hints


def _worst_skill(candidate: CandidateFeatures, needs: list[NeedView]) -> str | None:
    totals: dict[str, float] = {}
    counts: dict[str, int] = {}
    for need in needs:
        for skill, value in skill_coverages(need, candidate, list(need.must_skills)).items():
            totals[skill] = totals.get(skill, 0.0) + value
            counts[skill] = counts.get(skill, 0) + 1
    if not totals:
        for need in needs:
            if need.must_skills:
                return need.must_skills[0]
        return None
    return min(totals, key=lambda skill: (totals[skill] / counts[skill], skill))


def _mutate(candidate: CandidateFeatures, kind: str, needs: list[NeedView], today: date) -> CandidateFeatures:
    cloned = copy.deepcopy(candidate)
    if kind == "fresh":
        cloned.last_active_at = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        return cloned
    if kind == "fsp":
        discipline = cloned.specialization or "backend"
        cloned.fsp = list(cloned.fsp) + [FspFeature(discipline=discipline, event="ФСП", place=1, year=today.year)]
        return cloned
    skill = _worst_skill(cloned, needs) or "skill"
    embedding = None
    for need in needs:
        for requirement in need.requirements:
            if requirement.embedding and any(component != 0.0 for component in requirement.embedding):
                embedding = list(requirement.embedding)
                break
        if embedding is not None:
            break
    if embedding is None:
        embedding = [1.0, 0.0]
    cloned.skills = list(cloned.skills) + [SkillFeature(skill_id=skill, score=None, source="project")]
    cloned.evidence = list(cloned.evidence) + [
        EvidenceFeature(
            id=f"hint-{skill}",
            task=f"Проект с {skill}",
            domain=None,
            skills=[skill],
            role="owner",
            date=today,
            trust=1.0,
            embedding=embedding,
            origin="project",
        )
    ]
    return cloned


def _rank_hints(
    candidate: CandidateFeatures,
    needs: list[NeedView],
    peers: list[CandidateFeatures],
    today: date,
) -> list[dict[str, Any]]:
    sample = list(needs[:HINT_NEED_SAMPLE])
    rival = list(peers[:HINT_PEER_CAP])
    if not sample or not rival:
        return []
    pool_needs = [need for need in sample if _in_pool(need, candidate)]
    if not pool_needs:
        pool_needs = sample
    hints: list[dict[str, Any]] = []
    mutations = (
        ("fresh", "Решите задание", "Решить задание", "/candidate/test", HINT_EFFORT["mini_test"]),
        ("project", None, "Добавить проект", "/candidate/profile/edit#projects", HINT_EFFORT["project"]),
        ("fsp", "Свяжите ФСП ID", "Связать ФСП ID", "/candidate/profile/edit#fsp", HINT_EFFORT["conditions"]),
    )
    for kind, title_prefix, action, href, effort in mutations:
        mutated = _mutate(candidate, kind, pool_needs, today)
        before_places: list[int] = []
        after_places: list[int] = []
        for need in pool_needs:
            others = [score_breakdown(need, peer, today).s for peer in rival]
            before_places.append(_place(score_breakdown(need, candidate, today).s, others))
            after_places.append(_place(score_breakdown(need, mutated, today).s, others))
        before = _median_place(before_places)
        after = _median_place(after_places)
        if after >= before:
            continue
        effect = before - after
        if kind == "project":
            skill = _worst_skill(candidate, pool_needs) or "проект"
            title = f"Добавьте проект с {_label(skill)}: {before} → {after} место в категории"
            hint_id = f"rank:project:{skill}"
        else:
            title = f"{title_prefix}: {before} → {after} место в категории"
            hint_id = f"rank:{kind}"
        hints.append(
            _hint(
                hint_id,
                "rank",
                title,
                f"{before} → {after}",
                action,
                href,
                effect / effort,
            )
        )
    return hints


def build_candidate_hints(
    candidate: CandidateFeatures,
    needs: list[NeedView],
    peers: list[CandidateFeatures] | None = None,
    today: date | None = None,
) -> list[dict[str, Any]]:
    moment = today or _today()
    relevant = [need for need in needs if not candidate.specialization or need.specialization == candidate.specialization]
    hints = _blocker_hints(candidate, relevant)
    hints.extend(_rank_hints(candidate, relevant, list(peers or []), moment))
    hints.sort(key=lambda item: (-float(item["priority"]), str(item["id"])))
    return hints[:HINT_TOP]
