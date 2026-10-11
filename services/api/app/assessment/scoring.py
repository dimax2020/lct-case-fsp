"""Pure scoring for a finished attempt. Pending code counts as zero and does not block finish."""

from dataclasses import dataclass

from app.core.enums import GRADE_ORDER, Grade


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


def grade_for(score: float, declared: str) -> tuple[str, bool]:
    """Return (result grade, ready_for_next) from TEST-4 thresholds."""
    if score < 40:
        current = Grade(declared)
        index = GRADE_ORDER.index(current)
        lowered = GRADE_ORDER[index - 1] if index else current
        return lowered.value, False
    return Grade(declared).value, score >= 75


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
