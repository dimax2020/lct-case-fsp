"""NDCG@10 and the sim-threshold grid. No matching weights live here."""

from __future__ import annotations

import math
import re

TOKEN = re.compile(r"[0-9A-Za-zА-Яа-яЁё]{3,}")


def clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def binary_token_cosine(left: str, right: str) -> float:
    """Cosine of binary token sets. A stand-in for e5, not a replacement."""

    def tokens(text: str) -> set[str]:
        folded = text.casefold().replace("ё", "е")
        return set(TOKEN.findall(folded))

    first, second = tokens(left), tokens(right)
    if not first or not second:
        return 0.0
    return len(first & second) / math.sqrt(len(first) * len(second))


def dcg(relevances: list[int]) -> float:
    total = 0.0
    for index, relevance in enumerate(relevances, start=1):
        total += (2**relevance - 1) / math.log2(index + 1)
    return total


def ndcg_at_k(ranked_relevances: list[int], k: int = 10) -> float:
    window = ranked_relevances[:k]
    ideal = sorted(ranked_relevances, reverse=True)[:k]
    ideal_dcg = dcg(ideal)
    if ideal_dcg == 0:
        return 0.0
    return dcg(window) / ideal_dcg


def _average_ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    cursor = 0
    while cursor < len(values):
        end = cursor
        while end + 1 < len(values) and values[order[end + 1]] == values[order[cursor]]:
            end += 1
        average = (cursor + end) / 2 + 1
        for index in range(cursor, end + 1):
            ranks[order[index]] = average
        cursor = end + 1
    return ranks


def spearman(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or len(left) < 2:
        return 0.0
    left_ranks = _average_ranks(left)
    right_ranks = _average_ranks([float(item) for item in right])
    mean_left = sum(left_ranks) / len(left_ranks)
    mean_right = sum(right_ranks) / len(right_ranks)
    cov = sum((a - mean_left) * (b - mean_right) for a, b in zip(left_ranks, right_ranks, strict=True))
    var_left = sum((a - mean_left) ** 2 for a in left_ranks)
    var_right = sum((b - mean_right) ** 2 for b in right_ranks)
    if var_left == 0 or var_right == 0:
        return 0.0
    return cov / math.sqrt(var_left * var_right)


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, max(0, round(quantile * (len(ordered) - 1))))
    return ordered[index]


def fit_sim_thresholds(pairs: list[dict]) -> dict:
    """Stretch token cosine so weak pairs sit near 0 and strong pairs near 1.

    The grid that only maximises Spearman collapses to a step function. Here offset is the
    90th percentile of label-0 cosines (or 0 when that percentile is already tiny) and scale
    is the gap up to the 90th percentile of label-3 cosines. Do not copy the result into
    matching/config.py: embed() is still a zero vector, and e5 lives in a different range.
    """
    grouped: dict[int, list[float]] = {0: [], 1: [], 2: [], 3: []}
    cosines: list[float] = []
    labels: list[float] = []
    for pair in pairs:
        cosine = binary_token_cosine(pair["requirement"], pair["evidence"])
        cosines.append(cosine)
        labels.append(float(pair["label"]))
        grouped[int(pair["label"])].append(cosine)
    low = _percentile(grouped[0], 0.9)
    high = _percentile(grouped[3], 0.9)
    offset = round(low, 2) if low >= 0.05 else 0.0
    scale = round(max(0.05, high - offset), 2)
    sims = [clip((cosine - offset) / scale, 0.0, 1.0) for cosine in cosines]
    by_label: dict[str, list[float]] = {}
    for pair, sim in zip(pairs, sims, strict=True):
        by_label.setdefault(str(pair["label"]), []).append(sim)
    means = {label: round(sum(values) / len(values), 4) for label, values in sorted(by_label.items())}
    return {
        "n_pairs": 50 if len(pairs) == 50 else len(pairs),
        "embedding": "binary_token_cosine",
        "method": "label0_p90_to_zero__label3_p90_to_one",
        "sim_offset": offset,
        "sim_scale": scale,
        "spearman": round(spearman(sims, labels), 4),
        "spearman_raw_cosine": round(spearman(cosines, labels), 4),
        "mean_sim_by_label": means,
        "apply_to_config": False,
        "tz_defaults": {"sim_offset": 0.75, "sim_scale": 0.15},
        "note": (
            "Пороги растягивают косинус бинарных токенов: 90-й перцентиль пар с меткой 0 "
            "уходит в sim=0, 90-й перцентиль пар с меткой 3 — в sim=1. Это не multilingual-e5-base. "
            "embed() возвращает нулевой вектор, наблюдаемый косинус токенов не выше ~0.32, "
            "поэтому пороги ТЗ 0.75 и 0.15 обнулили бы все пары. В matching/config.py их не менять, "
            "пока агент D не прогонит эти же 50 пар через e5. apply_to_config=false."
        ),
    }
