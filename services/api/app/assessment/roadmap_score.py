"""Adaptive grade for a short roadmap sample. The latent value stays off the API."""

from app.core.enums import GRADE_ORDER, Grade

BAND = ("junior", "middle", "senior")
PROBES_PER_RUN = 3
COOLDOWN_UP_DAYS = 21
COOLDOWN_SAME_DAYS = 90
COOLDOWN_DOWN_DAYS = 120


def start_level(declared: str) -> str:
    """Intern and junior begin on junior items. Lead begins on senior items."""
    if declared in {"senior", "lead"}:
        return "senior"
    if declared == "middle":
        return "middle"
    return "junior"


def level_index(level: str) -> float:
    return float(BAND.index(level) + 1)


def check_score(values: list[str]) -> float:
    if not values:
        return 0.0
    weight = {"yes": 1.0, "unknown": 0.15, "no": 0.0}
    return sum(weight[item] for item in values) / len(values)


def concrete_score(answer: str, needles: tuple[str, ...], *, need: int = 2) -> float:
    folded = _fold(answer)
    if not folded or not needles:
        return 0.0
    hits = sum(1 for needle in needles if _fold(needle) in folded)
    return min(1.0, hits / need)


def block_score(checks: float, concrete: float) -> float:
    return 0.35 * checks + 0.65 * concrete


def next_level(level: str, block: float) -> str:
    index = BAND.index(level)
    if block >= 0.72 and index < len(BAND) - 1:
        return BAND[index + 1]
    if block <= 0.4 and index > 0:
        return BAND[index - 1]
    return level


def update_latent(latent: float, block: float) -> float:
    return max(0.5, min(3.6, latent + (block - 0.55) * 1.6))


def grade_from_latent(latent: float, declared: str) -> str:
    if latent < 1.45:
        return "intern" if declared == "intern" and latent < 1.15 else "junior"
    if latent < 2.45:
        return "middle"
    if latent >= 3.25 and declared == "lead":
        return "lead"
    return "senior"


def cooldown_for(declared: str, measured: str) -> tuple[int, str]:
    declared_index = GRADE_ORDER.index(Grade(declared))
    measured_index = GRADE_ORDER.index(Grade(measured))
    if measured_index > declared_index:
        return COOLDOWN_UP_DAYS, "up"
    if measured_index < declared_index:
        return COOLDOWN_DOWN_DAYS, "down"
    return COOLDOWN_SAME_DAYS, "same"


def study_items(
    checks: dict[str, str],
    statements: list[tuple[str, str]],
    concrete_answer: str | None,
    question: str,
    needles: tuple[str, ...],
) -> list[str]:
    """What to revisit: a «no», an «unknown», or a concrete answer that missed the point."""
    items: list[str] = []
    for check_id, text in statements:
        mark = checks.get(check_id)
        if mark == "no":
            items.append(text)
        elif mark == "unknown":
            items.append(f"{text}. Пока отмечено «не знаю».")
    if concrete_answer is not None and concrete_score(concrete_answer, needles) < 1:
        items.append(f"Разобрать вопрос: {question}")
    return items


def result_message(measured: str, outcome: str, days: int) -> str:
    label = _GRADE_RU[measured]
    if outcome == "up":
        return (
            f"По ответам ваш уровень ближе к {label}. "
            f"Поздравляем — следующий тест на этот уровень откроется через {days} дней, "
            "это короче обычных трёх месяцев."
        )
    if outcome == "down":
        return (
            f"По ответам уровень ближе к {label}. "
            f"Следующая попытка откроется через {days} дней: пауза длиннее обычной, "
            "чтобы закрыть пробелы по карте."
        )
    return f"Заявленный уровень совпал с ответами ({label}). Следующая попытка через {days} дней."


_GRADE_RU = {
    "intern": "Intern",
    "junior": "Junior",
    "middle": "Middle",
    "senior": "Senior",
    "lead": "Lead",
}


def _fold(text: str) -> str:
    lowered = text.strip().lower().replace("ё", "е")
    return "".join(char if char.isalnum() else " " for char in lowered)
