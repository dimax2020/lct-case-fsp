"""Pure scoring for a finished attempt. Pending code counts as zero and does not block finish."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.core.enums import GRADE_ORDER, Grade

GRADE_COOLDOWN = timedelta(days=90)


@dataclass(frozen=True)
class GradedTask:
    id: str
    kind: str
    skills: tuple[str, ...]
    answer: str | None


@dataclass(frozen=True)
class GradedAnswer:
    task_id: str
    answer: str | None
    skipped: bool
    verdict: str | None
    passed: int | None
    total: int | None


def grade_for(score: float, declared: str, current: str | None = None) -> tuple[str, bool]:
    """Return (kept grade, ready_for_next).

    A score under 40 does not lower the grade. The first assignment uses the
    declared grade whatever the score. ready_for_next is true only at 75+.
    """
    kept = Grade(current).value if current else Grade(declared).value
    return kept, score >= 75


def cooldown_active(changed_at: datetime | None, now: datetime) -> bool:
    """True when a grade change is still inside the 90-day window."""
    if changed_at is None:
        return False
    left = changed_at if changed_at.tzinfo is not None else changed_at.replace(tzinfo=UTC)
    right = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
    return right - left < GRADE_COOLDOWN


def neighbor_grade(current: str, direction: str) -> str:
    """Next grade up or down the official scale. Raises ValueError at the edge."""
    if direction not in {"up", "down"}:
        raise ValueError(direction)
    index = GRADE_ORDER.index(Grade(current))
    nxt = index + 1 if direction == "up" else index - 1
    if nxt < 0 or nxt >= len(GRADE_ORDER):
        raise ValueError(direction)
    return GRADE_ORDER[nxt].value


def task_fraction(task: GradedTask, answer: GradedAnswer | None) -> float:
    if answer is None or answer.skipped:
        return 0.0
    if task.kind == "mcq":
        return 1.0 if answer.answer == task.answer else 0.0
    if answer.verdict == "PENDING":
        return 0.0
    total = answer.total or 0
    if total <= 0:
        return 0.0
    return max(0.0, min(1.0, (answer.passed or 0) / total))


def score_attempt(tasks: list[GradedTask], answers: list[GradedAnswer]) -> tuple[float, dict[str, float]]:
    if not tasks:
        return 0.0, {}
    by_task = {item.task_id: item for item in answers}
    fractions = [task_fraction(task, by_task.get(task.id)) for task in tasks]
    score = round(100.0 * sum(fractions) / len(tasks), 2)
    buckets: dict[str, list[float]] = {}
    for task, fraction in zip(tasks, fractions, strict=True):
        for skill in task.skills:
            buckets.setdefault(skill, []).append(fraction * 100.0)
    skill_scores = {skill: round(sum(values) / len(values), 2) for skill, values in buckets.items()}
    return score, skill_scores
