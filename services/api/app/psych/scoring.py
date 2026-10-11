"""Подсчёт результатов теста рабочего стиля. Чистые функции, без БД и без FastAPI.

Шаги совпадают с разделом «Ключ и подсчёт результатов» бланка:

1. Часть 1 (DISC): «+» даёт шкале +1, «−» даёт −1; сумма шкалы от −12 до +12,
   сумма всех четырёх шкал всегда 0; процент = (сумма + 12) / 24 × 100.
2. Часть 2: прямые пункты — балл = ответ, обратные — 6 − ответ; суммы по шкалам.
   Социальная желательность считается отдельно и в шкалы не входит.
3. Часть 3: выбранная буква даёт баллы двум шкалам (0–3).
4. Сырой балл = часть 2 + часть 3; процент = (сырой − мин) / (макс − мин) × 100.
5. Уровень: ≤33 низкий, ≤66 средний, иначе высокий.
6. Индекс соответствия = Σ(вес × %шкалы) / 100 по округлённым процентам.

Пропуски: в части 2 пропущенный пункт заменяется средним баллом остальных пунктов
той же шкалы (как предписывает ключ). Пропущенная ситуация заменяется средним
баллом вариантов этой ситуации. Пропущенный блок DISC не даёт баллов ни одной шкале.
Больше трёх пропусков — флаг «тест лучше пройти заново».

Округление везде арифметическое (0,5 вверх), как в ручном подсчёте, а не банковское.
"""

import math
from typing import Any

from app.psych import bank

Answers = dict[str, Any]


def round_half_up(value: float) -> int:
    return int(math.floor(value + 0.5))


def level_of(pct: int) -> str:
    if pct <= bank.LEVEL_LOW_MAX:
        return "low"
    if pct <= bank.LEVEL_MID_MAX:
        return "mid"
    return "high"


def fit_level(index: int) -> str:
    if index >= 70:
        return "high"
    if index >= 50:
        return "mid"
    return "low"


# ---------------------------------------------------------------- нормализация ответов


def _letter(value: Any) -> str | None:
    if isinstance(value, str) and value in bank.LETTERS:
        return value
    return None


def clean_answers(raw: Any) -> Answers:
    """Оставляет только допустимые ответы. Неверные значения считаются пропуском."""
    data = raw if isinstance(raw, dict) else {}
    disc: dict[str, dict[str, str]] = {}
    raw_disc = data.get("disc") if isinstance(data.get("disc"), dict) else {}
    for block_id in range(1, len(bank.DISC_BLOCKS) + 1):
        item = raw_disc.get(str(block_id)) if isinstance(raw_disc, dict) else None
        if not isinstance(item, dict):
            continue
        most = _letter(item.get("most"))
        least = _letter(item.get("least"))
        entry: dict[str, str] = {}
        if most:
            entry["most"] = most
        if least and least != most:
            entry["least"] = least
        if entry:
            disc[str(block_id)] = entry
    statements: dict[str, int] = {}
    raw_statements = data.get("statements") if isinstance(data.get("statements"), dict) else {}
    for number in range(1, len(bank.STATEMENTS) + 1):
        value = raw_statements.get(str(number)) if isinstance(raw_statements, dict) else None
        if isinstance(value, bool):
            continue
        if isinstance(value, int) and 1 <= value <= 5:
            statements[str(number)] = value
    cases: dict[str, str] = {}
    raw_cases = data.get("cases") if isinstance(data.get("cases"), dict) else {}
    for number in range(1, len(bank.CASES) + 1):
        letter = _letter(raw_cases.get(str(number)) if isinstance(raw_cases, dict) else None)
        if letter:
            cases[str(number)] = letter
    return {"disc": disc, "statements": statements, "cases": cases}


def progress(answers: Answers) -> dict[str, int]:
    clean = clean_answers(answers)
    blocks = sum(1 for item in clean["disc"].values() if "most" in item and "least" in item)
    return {
        "blocks_done": blocks,
        "blocks_total": len(bank.DISC_BLOCKS),
        "statements_done": len(clean["statements"]),
        "statements_total": len(bank.STATEMENTS),
        "cases_done": len(clean["cases"]),
        "cases_total": len(bank.CASES),
    }


# ---------------------------------------------------------------- шаг 1: DISC


def disc_sums(answers: Answers) -> tuple[dict[str, int], int]:
    """Суммы D/I/S/C и число неполных блоков (без «+» или без «−»)."""
    sums = {scale: 0 for scale in bank.DISC_SCALES}
    skipped = 0
    for block_id, block in enumerate(bank.DISC_BLOCKS, start=1):
        item = answers["disc"].get(str(block_id)) or {}
        most, least = item.get("most"), item.get("least")
        if not most or not least:
            skipped += 1
            continue
        sums[block[bank.LETTERS.index(most)][1]] += 1
        sums[block[bank.LETTERS.index(least)][1]] -= 1
    return sums, skipped


def disc_pct(total: int) -> int:
    return round_half_up((total + 12) / 24 * 100)


_COLOR_PREFIX = {"D": "Красно", "I": "Жёлто", "S": "Зелёно", "C": "Сине"}


def disc_profile(sums: dict[str, int]) -> dict[str, Any]:
    """Основной и вторичный цвет по правилам ключа."""
    if all(-2 <= value <= 2 for value in sums.values()):
        return {"balanced": True, "primary": [], "secondary": [], "label": "Сбалансированный профиль"}
    ordered = sorted(bank.DISC_SCALES, key=lambda scale: (-sums[scale], bank.DISC_SCALES.index(scale)))
    top = sums[ordered[0]]
    tied = [scale for scale in ordered if sums[scale] == top]
    if len(tied) >= 2:
        names = [bank.DISC_INFO[scale]["color_name"].lower() for scale in tied]
        label = " и ".join(names).capitalize() + " (равнозначно)"
        return {"balanced": False, "primary": tied, "secondary": [], "label": label}
    primary = ordered[0]
    rest = ordered[1:]
    second_value = sums[rest[0]]
    secondary: list[str] = []
    if second_value > 0 and top - second_value <= 3:
        secondary = [scale for scale in rest if sums[scale] == second_value]
    if secondary:
        label = _COLOR_PREFIX[primary] + "-" + bank.DISC_INFO[secondary[0]]["color_name"].lower()
        if len(secondary) > 1:
            label += " / " + bank.DISC_INFO[secondary[1]]["color_name"].lower()
    else:
        label = bank.DISC_INFO[primary]["color_name"]
    return {"balanced": False, "primary": [primary], "secondary": secondary, "label": label}


# ---------------------------------------------------------------- шаг 2: утверждения


def _statement_points(number: int, answer: int, reverse: bool) -> int:
    return 6 - answer if reverse else answer


def statement_sums(answers: Answers) -> tuple[dict[str, float], float, int]:
    """Суммы по шкалам, сумма социальной желательности и число пропусков в части 2."""
    given = answers["statements"]
    sums: dict[str, float] = {}
    for scale, key in bank.STATEMENT_KEY.items():
        items = [(number, False) for number in key["direct"]] + [(number, True) for number in key["reverse"]]
        sums[scale] = _sum_with_imputation(given, items)
    social = _sum_with_imputation(given, [(number, False) for number in bank.SOCIAL_DESIRABILITY_ITEMS])
    skipped = len(bank.STATEMENTS) - len(given)
    return sums, social, skipped


def _sum_with_imputation(given: dict[str, int], items: list[tuple[int, bool]]) -> float:
    points = [_statement_points(number, given[str(number)], reverse) for number, reverse in items if str(number) in given]
    missing = len(items) - len(points)
    if not points:
        return 3.0 * len(items)
    mean = sum(points) / len(points)
    return float(sum(points)) + mean * missing


def statement_bounds(scale: str) -> tuple[int, int]:
    key = bank.STATEMENT_KEY[scale]
    count = len(key["direct"]) + len(key["reverse"])
    return count, count * 5


# ---------------------------------------------------------------- шаг 3: ситуации


def case_sums(answers: Answers) -> tuple[dict[str, float], int]:
    sums = {scale: 0.0 for scale in bank.SCALES}
    skipped = 0
    for number, case in enumerate(bank.CASES, start=1):
        first, second = case["scales"]
        letter = answers["cases"].get(str(number))
        if letter is None:
            skipped += 1
            sums[first] += sum(point[0] for point in case["points"]) / len(case["points"])
            sums[second] += sum(point[1] for point in case["points"]) / len(case["points"])
            continue
        points = case["points"][bank.LETTERS.index(letter)]
        sums[first] += points[0]
        sums[second] += points[1]
    return sums, skipped


def case_bounds(scale: str) -> tuple[int, int]:
    low = high = 0
    for case in bank.CASES:
        for slot, name in enumerate(case["scales"]):
            if name == scale:
                values = [point[slot] for point in case["points"]]
                low += min(values)
                high += max(values)
    return low, high


# ---------------------------------------------------------------- шаг 4–6


def scale_bounds(scale: str) -> tuple[int, int]:
    s_low, s_high = statement_bounds(scale)
    c_low, c_high = case_bounds(scale)
    return s_low + c_low, s_high + c_high


def scale_pct(raw: float, scale: str) -> int:
    low, high = scale_bounds(scale)
    pct = round_half_up((raw - low) / (high - low) * 100)
    return max(0, min(100, pct))


def fit_index(percents: dict[str, int], weights: dict[str, int]) -> int:
    return round_half_up(sum(weights[scale] * percents[scale] for scale in bank.SCALES) / 100)


def straight_line_run(answers: Answers) -> int:
    best = run = 0
    previous: int | None = None
    for number in range(1, len(bank.STATEMENTS) + 1):
        value = answers["statements"].get(str(number))
        if value is None:
            run, previous = 0, None
            continue
        run = run + 1 if value == previous else 1
        previous = value
        best = max(best, run)
    return best


def _number(value: float) -> float | int:
    rounded = round_half_up(value * 10) / 10
    return int(rounded) if rounded == int(rounded) else rounded


def score(raw_answers: Any, duration_seconds: float | None = None) -> dict[str, Any]:
    answers = clean_answers(raw_answers)

    sums, disc_skipped = disc_sums(answers)
    disc = [
        {
            "scale": scale,
            "sum": sums[scale],
            "pct": disc_pct(sums[scale]),
            **bank.DISC_INFO[scale],
        }
        for scale in bank.DISC_SCALES
    ]

    statement_part, social_sum, statements_skipped = statement_sums(answers)
    case_part, cases_skipped = case_sums(answers)
    scales = []
    percents: dict[str, int] = {}
    for scale in bank.SCALES:
        raw = statement_part[scale] + case_part[scale]
        low, high = scale_bounds(scale)
        pct = scale_pct(raw, scale)
        percents[scale] = pct
        level = level_of(pct)
        scales.append(
            {
                "scale": scale,
                "title": bank.SCALE_INFO[scale]["title"],
                "statements": _number(statement_part[scale]),
                "situations": _number(case_part[scale]),
                "raw": _number(raw),
                "min": low,
                "max": high,
                "pct": pct,
                "level": level,
                "level_title": bank.LEVEL_TEXT[level][0],
                "level_text": bank.LEVEL_TEXT[level][1],
            }
        )

    social_pct = max(0, min(100, round_half_up((social_sum - 4) / 16 * 100)))
    social_flag = social_sum >= bank.SOCIAL_DESIRABILITY_FLAG

    skips = disc_skipped + statements_skipped + cases_skipped
    run = straight_line_run(answers)
    flags = []
    if social_flag:
        flags.append({"id": "social_desirability",
                      "text": f"Социальная желательность {_number(social_sum)} из 20: возможно приукрашивание, "
                              "уточните результаты на интервью."})
    if run >= bank.STRAIGHT_LINE_RUN:
        flags.append({"id": "straight_line", "text": f"{run} одинаковых ответов подряд в части 2."})
    if duration_seconds is not None:
        minutes = duration_seconds / 60
        if minutes < bank.MIN_MINUTES:
            flags.append({"id": "too_fast", "text": f"Тест пройден за {max(1, round_half_up(minutes))} мин — быстрее 8 минут."})
        elif minutes > bank.MAX_MINUTES:
            flags.append(
                {"id": "too_slow", "text": f"Тест занял {round_half_up(minutes)} мин — дольше 40 минут, вероятно с перерывами."}
            )
    if skips > bank.MAX_SKIPS:
        flags.append({"id": "skips", "text": f"Пропущено пунктов: {skips}. Тест лучше пройти заново."})

    fits = []
    for profile in bank.FIT_PROFILES:
        index = fit_index(percents, profile["weights"])
        level = fit_level(index)
        fits.append(
            {
                "id": profile["id"],
                "title": profile["title"],
                "disc": profile["disc"],
                "weights": dict(profile["weights"]),
                "index": index,
                "level": level,
                "level_title": {"high": "Высокое", "mid": "Среднее", "low": "Низкое"}[level],
            }
        )

    return {
        "version": bank.VERSION,
        "disc": disc,
        "disc_check": sum(sums.values()),
        "disc_profile": disc_profile(sums),
        "scales": scales,
        "social_desirability": {"sum": _number(social_sum), "pct": social_pct, "flag": social_flag},
        "fits": fits,
        "flags": flags,
        "skipped": {"disc": disc_skipped, "statements": statements_skipped, "cases": cases_skipped, "total": skips},
        "duration_seconds": None if duration_seconds is None else int(duration_seconds),
        "reliable": not flags,
    }


def candidate_view(result: dict[str, Any]) -> dict[str, Any]:
    """Кандидат видит свой стиль, шкалы и индексы. Флаги надёжности и сырые баллы — только HR."""
    view = {key: result[key] for key in ("version", "disc", "disc_profile", "fits") if key in result}
    view["scales"] = [
        {key: item[key] for key in ("scale", "title", "pct", "level", "level_title", "level_text")}
        for item in result.get("scales", [])
    ]
    return view
