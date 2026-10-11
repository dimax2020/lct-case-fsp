"""Live IRT 2PL CAT: EAP on a theta grid, Fisher information, exposure cap, border block.

Formulas match tmp_bank/sim.py. Binary response x uses the 0.75 solve threshold from the bank."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from app.core.enums import GRADE_ORDER, Grade

CUTS = np.array([-1.2, 0.2, 1.2], dtype=float)
GRID = np.linspace(-4.0, 4.0, 161)
PRIOR = np.exp(-(GRID**2) / 2.0)
PRIOR = PRIOR / PRIOR.sum()

MIN_LEN = 8
MAX_LEN = 20
SE_STOP = 0.30
TOPK = 5
EXPOSURE_CAP = 0.25
EXPOSURE_WARMUP = 50
BORDER_EXTRA = 5
SOLVE_THRESHOLD = 0.75

START_THETA: dict[str, float] = {
    Grade.intern.value: -2.2,
    Grade.junior.value: -1.8,
    Grade.middle.value: -0.5,
    Grade.senior.value: 0.7,
    Grade.lead.value: 1.8,
}

Decision = Literal["passed", "above", "borderline", "below"]


def p2pl(theta: np.ndarray | float, a: np.ndarray | float, b: np.ndarray | float) -> np.ndarray | float:
    return 1.0 / (1.0 + np.exp(-1.7 * a * (theta - b)))


def fisher(theta: float, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    p = np.asarray(p2pl(theta, a, b), dtype=float)
    return (1.7 * a) ** 2 * p * (1.0 - p)


def start_theta(declared: str) -> float:
    return START_THETA.get(declared, -0.5)


def grade_from_theta(theta: float) -> str:
    if theta >= 2.2:
        return Grade.lead.value
    index = int(np.searchsorted(CUTS, theta, side="right"))
    return (Grade.intern.value, Grade.junior.value, Grade.middle.value, Grade.senior.value)[index]


def nearest_cut(theta: float) -> float:
    return float(CUTS[int(np.argmin(np.abs(CUTS - theta)))])


def theta_to_score(theta: float) -> float:
    return round(float(max(0.0, min(100.0, (theta + 3.0) * (100.0 / 6.0)))), 2)


def theta_to_percentile(theta: float) -> float:
    return round(float(100.0 / (1.0 + np.exp(-theta))), 1)


def eap(responses: list[tuple[float, float, float]]) -> tuple[float, float]:
    """responses: (a, b, x) where x is 1/0 or a partial in [0, 1]."""
    post = PRIOR.copy()
    for a, b, x in responses:
        like = np.asarray(p2pl(GRID, a, b), dtype=float)
        if x >= SOLVE_THRESHOLD:
            post *= like
        else:
            post *= 1.0 - like
        total = float(post.sum())
        if total <= 0:
            post = PRIOR.copy()
            break
        post /= total
    theta = float((GRID * post).sum())
    se = float(np.sqrt(((GRID - theta) ** 2 * post).sum()))
    return theta, se


def prior_eap(declared: str) -> tuple[float, float]:
    start = start_theta(declared)
    post = PRIOR * np.exp(-((GRID - start) ** 2) / 2.0)
    post /= post.sum()
    theta = float((GRID * post).sum())
    se = float(np.sqrt(((GRID - theta) ** 2 * post).sum()))
    return theta, se


@dataclass(frozen=True)
class Selection:
    index: int
    target: float


def allowed_mask(
    shown: np.ndarray,
    tests: int,
    used: list[int],
    cap: float = EXPOSURE_CAP,
    warmup: int = EXPOSURE_WARMUP,
) -> np.ndarray:
    mask = np.ones(len(shown), dtype=bool)
    mask[used] = False
    if cap < 1 and tests >= warmup:
        mask &= shown / max(tests, 1) < cap
    if not mask.any():
        mask = np.ones(len(shown), dtype=bool)
        mask[used] = False
    return mask


def select_item(
    theta: float,
    a: np.ndarray,
    b: np.ndarray,
    shown: np.ndarray,
    tests: int,
    used: list[int],
    rng: np.random.Generator,
    *,
    target: float | None = None,
    topk: int = TOPK,
) -> Selection | None:
    aim = float(theta if target is None else target)
    mask = allowed_mask(shown, tests, used)
    if not mask.any():
        return None
    idx = np.flatnonzero(mask)
    info = fisher(aim, a[idx], b[idx])
    order = np.argsort(-info)
    k = min(topk, len(order))
    pick = int(idx[int(order[int(rng.integers(0, k))])])
    return Selection(index=pick, target=aim)


def should_stop(n: int, se: float, min_len: int = MIN_LEN, se_stop: float = SE_STOP) -> bool:
    return n >= min_len and se < se_stop


def in_border(theta: float, se: float) -> bool:
    return abs(theta - nearest_cut(theta)) < se


@dataclass(frozen=True)
class GradeDecision:
    assigned: str
    measured: str
    ready_for_next: bool
    decision: Decision
    borderline: bool
    message: str


def decide_grade(
    theta: float,
    se: float,
    declared: str,
    current: str | None,
    *,
    grade_change: bool = False,
) -> GradeDecision:
    measured = grade_from_theta(theta)
    borderline = in_border(theta, se)
    declared_i = GRADE_ORDER.index(Grade(declared))
    measured_i = GRADE_ORDER.index(Grade(measured))
    if borderline:
        decision: Decision = "borderline"
    elif measured_i > declared_i:
        decision = "above"
    elif measured_i < declared_i:
        decision = "below"
    else:
        decision = "passed"

    if grade_change and measured_i >= declared_i:
        assigned = declared
    elif current is None:
        assigned = measured
    else:
        assigned = current

    assigned_i = GRADE_ORDER.index(Grade(assigned))
    ready = measured_i > assigned_i
    message = _message(decision, declared, measured, assigned, borderline)
    return GradeDecision(
        assigned=assigned,
        measured=measured,
        ready_for_next=ready,
        decision=decision,
        borderline=borderline,
        message=message,
    )


def _message(decision: Decision, declared: str, measured: str, assigned: str, borderline: bool) -> str:
    labels = {
        Grade.intern.value: "Intern",
        Grade.junior.value: "Junior",
        Grade.middle.value: "Middle",
        Grade.senior.value: "Senior",
        Grade.lead.value: "Lead",
    }
    d, m, a = labels[declared], labels[measured], labels[assigned]
    if decision == "above":
        return f"Заявлен {d}, оценка уверенно выше: {m}. Категория остаётся {a}, можно пройти тест на грейд выше."
    if decision == "below":
        return f"Заявлен {d}, оценка ниже: {m}. Принудительного понижения нет: категория {a}. Можно пройти тест на грейд ниже."
    if decision == "borderline" or borderline:
        return f"Пограничная зона у порога грейда. Заявлен {d}, оценка {m}, категория {a}."
    return f"Грейд подтверждён: {a}. Оценка совпадает с заявленным {d}."
