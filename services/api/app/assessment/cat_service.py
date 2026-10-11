"""CAT sessions on top of existing /assessment/attempts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import numpy as np
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.assessment import cat_engine
from app.assessment.cat_engine import GradeDecision
from app.assessment.item_bank import SUPPORTED, PlayableItem, item_by_id, items_for, skills_of, upsert_items
from app.assessment.models import Attempt, AttemptAnswer, CatExposure
from app.assessment.schemas import (
    AnswerIn,
    AttemptProgress,
    AttemptResult,
    AttemptView,
    EligibilityOut,
    SkillScore,
    TaskOption,
    TaskPublic,
)
from app.core.errors import AppError

CAT_MINUTES = 90
RETRY_DAYS = 30
_schema_ready = False


def timer_enabled() -> bool:
    from os import environ

    return environ.get("ASSESSMENT_TIMER", "off") == "on"


def cooldown_enabled() -> bool:
    from os import environ

    return environ.get("ASSESSMENT_COOLDOWN", "on") != "off"


async def ensure_schema(session: AsyncSession) -> None:
    """Create CAT columns/tables if alembic 009 has not been applied yet."""
    global _schema_ready
    if _schema_ready:
        return
    await session.execute(text("ALTER TABLE attempts ADD COLUMN IF NOT EXISTS cat jsonb"))
    await session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS cat_exposure (
                template_id varchar(64) PRIMARY KEY,
                shown integer NOT NULL DEFAULT 0
            )
            """
        )
    )
    await session.commit()
    _schema_ready = True


def engine_enabled() -> bool:
    from os import environ

    from app.assessment import item_bank

    if environ.get("ASSESSMENT_ENGINE", "cat") == "yaml":
        return False
    return item_bank.available()


def is_cat(attempt: Attempt) -> bool:
    return isinstance(attempt.cat, dict) and attempt.cat.get("engine") == "cat"


def to_public(item: PlayableItem) -> TaskPublic:
    options = [TaskOption(id=row["id"], text=row["text"]) for row in item.options] if item.options else None
    return TaskPublic(
        id=item.id,
        kind=item.kind,  # type: ignore[arg-type]
        skills=list(skills_of(item)),
        difficulty=item.difficulty,
        body=item.body,
        options=options,
        tests_public=None,
        languages=list(item.languages),
        title=item.title,
        format=item.format,
        time_minutes=item.time,
        tags=list(item.tags),
        multiple=item.multiple,
        snippet=item.snippet or None,
        placeholder=item.placeholder or None,
    )


def _state(attempt: Attempt) -> dict[str, Any]:
    raw = attempt.cat if isinstance(attempt.cat, dict) else {}
    return dict(raw)


def _write(attempt: Attempt, state: dict[str, Any]) -> None:
    attempt.cat = state
    flag_modified(attempt, "cat")


def _remaining(deadline: datetime, *, finished: bool) -> int:
    if finished:
        return 0
    value = deadline if deadline.tzinfo else deadline.replace(tzinfo=UTC)
    return max(0, int((value - datetime.now(UTC)).total_seconds()))


def _arrays(items: tuple[PlayableItem, ...]) -> tuple[np.ndarray, np.ndarray, list[str]]:
    return (
        np.array([item.a for item in items], dtype=float),
        np.array([item.b for item in items], dtype=float),
        [item.id for item in items],
    )


async def _exposure(session: AsyncSession, ids: list[str]) -> tuple[np.ndarray, int]:
    rows = {
        row.template_id: row.shown
        for row in (await session.scalars(select(CatExposure).where(CatExposure.template_id.in_(ids)))).all()
    }
    shown = np.array([float(rows.get(item_id, 0)) for item_id in ids], dtype=float)
    finished_cat = select(func.count()).select_from(Attempt).where(Attempt.finished_at.is_not(None), Attempt.cat.is_not(None))
    tests = int(await session.scalar(finished_cat) or 0)
    return shown, tests


async def _commit_exposure(session: AsyncSession, used: list[str]) -> None:
    existing = {
        row.template_id: row
        for row in (await session.scalars(select(CatExposure).where(CatExposure.template_id.in_(used)))).all()
    }
    for item_id in used:
        row = existing.get(item_id)
        if row is None:
            session.add(CatExposure(template_id=item_id, shown=1))
        else:
            row.shown += 1


def _responses(items: tuple[PlayableItem, ...], correct: dict[str, float]) -> list[tuple[float, float, float]]:
    by_id = {item.id: item for item in items}
    out: list[tuple[float, float, float]] = []
    for item_id, value in correct.items():
        item = by_id.get(item_id)
        if item is None:
            continue
        out.append((item.a, item.b, float(value)))
    return out


def _pick(items: tuple[PlayableItem, ...], state: dict[str, Any], shown: np.ndarray, tests: int) -> PlayableItem | None:
    a, b, ids = _arrays(items)
    used = [ids.index(item_id) for item_id in state.get("used") or [] if item_id in ids]
    rng = np.random.default_rng(int(state.get("seed") or 1))
    target = None
    if state.get("phase") == "border":
        target = cat_engine.nearest_cut(float(state.get("theta") or 0))
    picked = cat_engine.select_item(
        float(state.get("theta") or 0),
        a,
        b,
        shown,
        tests,
        used,
        rng,
        target=target,
    )
    if picked is None:
        return None
    return items[picked.index]


def _progress(state: dict[str, Any], *, finished: bool) -> AttemptProgress:
    used = list(state.get("used") or [])
    current = None if finished else state.get("current")
    answered = len(used)
    cursor = answered + (1 if current else 0)
    total = answered if finished else cat_engine.MAX_LEN
    return AttemptProgress(current=max(cursor, 1 if not finished else 0), total=max(total, 1), answered=answered, skipped=0)


def _skill_scores(items: tuple[PlayableItem, ...], correct: dict[str, float]) -> dict[str, float]:
    buckets: dict[str, list[float]] = {}
    by_id = {item.id: item for item in items}
    for item_id, value in correct.items():
        item = by_id.get(item_id)
        if item is None:
            continue
        for skill in skills_of(item):
            buckets.setdefault(skill, []).append(float(value) * 100.0)
    return {tag: round(sum(values) / len(values), 2) for tag, values in buckets.items()}


def _result_payload(
    attempt: Attempt,
    decision: GradeDecision,
    score: float,
    skills: dict[str, float],
    rank: int | None,
    size: int | None,
) -> AttemptResult:
    state = _state(attempt)
    return AttemptResult(
        score=score,
        grade=decision.assigned,  # type: ignore[arg-type]
        ready_for_next=decision.ready_for_next,
        skill_scores=[SkillScore(skill_id=key, score=value) for key, value in sorted(skills.items())],
        rank=rank,
        category_size=size,
        theta=float(state.get("theta") or 0),
        se=float(state.get("se") or 0),
        decision=decision.decision,
        measured_grade=decision.measured,  # type: ignore[arg-type]
        percentile=cat_engine.theta_to_percentile(float(state.get("theta") or 0)),
        message=decision.message,
    )


def _task_view(state: dict[str, Any], *, finished: bool) -> TaskPublic | None:
    if finished:
        return None
    current = state.get("current")
    if not current:
        return None
    item = item_by_id(str(current))
    return to_public(item) if item else None


def view_from(
    attempt: Attempt,
    *,
    result: AttemptResult | None = None,
) -> AttemptView:
    state = _state(attempt)
    finished = attempt.finished_at is not None
    return AttemptView(
        id=attempt.id,
        specialization=attempt.specialization,  # type: ignore[arg-type]
        declared_grade=attempt.declared_grade,  # type: ignore[arg-type]
        started_at=attempt.started_at,
        deadline_at=attempt.deadline_at,
        finished_at=attempt.finished_at,
        remaining_seconds=_remaining(attempt.deadline_at, finished=finished),
        progress=_progress(state, finished=finished),
        task=_task_view(state, finished=finished),
        result=result,
        engine="cat",
        theta=float(state.get("theta") or 0) if state else None,
        se=float(state.get("se") or 0) if state else None,
        decision=state.get("decision"),
        measured_grade=state.get("measured_grade"),
        percentile=state.get("percentile"),
        message=state.get("message"),
        timer_enabled=timer_enabled(),
        time_limit_minutes=CAT_MINUTES,
    )


async def heal(session: AsyncSession, attempt: Attempt) -> None:
    """Replace the current item if it left the playable set (bank was updated mid-attempt)."""
    if attempt.finished_at is not None:
        return
    state = _state(attempt)
    items = items_for(attempt.specialization)
    current = state.get("current")
    if not items or (current and any(item.id == current for item in items)):
        return
    await upsert_items(session, items)
    shown, tests = await _exposure(session, [item.id for item in items])
    nxt = _pick(items, state, shown, tests)
    state["current"] = nxt.id if nxt else None
    _write(attempt, state)
    await session.commit()


async def _drop_legacy(session: AsyncSession, candidate_id: UUID) -> None:
    """Unfinished YAML attempts cannot continue under CAT and would block the start."""
    await session.execute(
        text("DELETE FROM attempts WHERE candidate_id = CAST(:id AS uuid) AND finished_at IS NULL AND cat IS NULL"),
        {"id": str(candidate_id)},
    )
    await session.commit()


async def _open_attempt(session: AsyncSession, candidate_id: UUID) -> Attempt | None:
    await _drop_legacy(session, candidate_id)
    return await session.scalar(
        select(Attempt)
        .where(Attempt.candidate_id == candidate_id, Attempt.finished_at.is_(None))
        .order_by(Attempt.started_at.desc())
    )


async def _last_finished(session: AsyncSession, candidate_id: UUID) -> Attempt | None:
    return await session.scalar(
        select(Attempt)
        .where(Attempt.candidate_id == candidate_id, Attempt.finished_at.is_not(None))
        .order_by(Attempt.finished_at.desc())
    )


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


async def eligibility(session: AsyncSession, candidate_id: UUID) -> EligibilityOut:
    await ensure_schema(session)
    open_row = await _open_attempt(session, candidate_id)
    if open_row is not None:
        return EligibilityOut(
            can_start=False,
            reason="session_active",
            active_attempt_id=open_row.id,
            message="Уже есть незаконченный тест — продолжите его.",
        )
    found = await session.execute(
        text("SELECT grade, grade_changed_at FROM candidates WHERE id = CAST(:id AS uuid)"),
        {"id": str(candidate_id)},
    )
    _grade, changed_at = found.one()
    now = datetime.now(UTC)
    changed = _aware(changed_at if isinstance(changed_at, datetime) else None)
    last = await _last_finished(session, candidate_id)
    finished = _aware(last.finished_at) if last else None
    locked = (
        cooldown_enabled()
        and last is not None
        and is_cat(last)
        and finished is not None
        and now - finished < timedelta(days=RETRY_DAYS)
        and not last.grade_change
    )
    if locked and finished is not None:
        unlock = finished + timedelta(days=RETRY_DAYS)
        return EligibilityOut(
            can_start=False,
            reason="retry_cooldown",
            retry_at=unlock,
            grade_change_at=changed + timedelta(days=90) if changed is not None else None,
            message="Повтор на тот же грейд — через 30 дней.",
        )
    if not cooldown_enabled():
        return EligibilityOut(
            can_start=True,
            message="Пересдачу можно начать сразу. В рабочем режиме: повтор через 30 дней, смена грейда раз в 90.",
        )
    return EligibilityOut(
        can_start=True,
        grade_change_at=changed + timedelta(days=90) if changed is not None else None,
        message="Можно начать адаптивный тест.",
    )


async def start(
    session: AsyncSession,
    candidate_id: UUID,
    specialization: str,
    declared_grade: str,
    *,
    grade_change: bool = False,
) -> Attempt:
    await ensure_schema(session)
    if specialization not in SUPPORTED:
        raise AppError("specialization_unavailable", "Тест пока доступен только для Backend и Frontend", status_code=400)
    if not grade_change:
        gate = await eligibility(session, candidate_id)
        if not gate.can_start and gate.reason == "session_active" and gate.active_attempt_id:
            existing = await session.get(Attempt, gate.active_attempt_id)
            if existing is not None:
                return existing
        if not gate.can_start:
            code = gate.reason or "cooldown_active"
            raise AppError(code, gate.message or "Сейчас тест недоступен", status_code=409)
    else:
        open_row = await _open_attempt(session, candidate_id)
        if open_row is not None:
            return open_row

    items = items_for(specialization)
    if len(items) < cat_engine.MIN_LEN:
        raise AppError("task_bank_invalid", "В банке недостаточно заданий для этой специализации", status_code=500)
    await upsert_items(session, items)
    theta, se = cat_engine.prior_eap(declared_grade)
    seed = int(candidate_id.int % (2**32)) ^ int(datetime.now(UTC).timestamp())
    state: dict[str, Any] = {
        "engine": "cat",
        "theta": theta,
        "se": se,
        "used": [],
        "correct": {},
        "current": None,
        "phase": "main",
        "border_left": cat_engine.BORDER_EXTRA,
        "seed": seed,
    }
    shown, tests = await _exposure(session, [item.id for item in items])
    current = _pick(items, state, shown, tests)
    if current is None:
        raise AppError("task_bank_invalid", "Не удалось выбрать первое задание", status_code=500)
    state["current"] = current.id
    started = datetime.now(UTC)
    attempt = Attempt(
        candidate_id=candidate_id,
        specialization=specialization,
        declared_grade=declared_grade,
        started_at=started,
        deadline_at=started + timedelta(minutes=CAT_MINUTES),
        grade_change=grade_change,
        cat=state,
    )
    session.add(attempt)
    await session.commit()
    await session.refresh(attempt)
    return attempt


async def answer(session: AsyncSession, attempt: Attempt, body: AnswerIn) -> tuple[Attempt, bool]:
    state = _state(attempt)
    current_id = str(state.get("current") or "")
    if not current_id:
        raise AppError("item_already_answered", "Текущего задания нет", status_code=409)
    if body.task_id != current_id:
        raise AppError("task_not_found", "Ответьте на текущее задание", status_code=404)
    item = item_by_id(current_id)
    if item is None:
        raise AppError("task_not_found", "Задание не найдено", status_code=404)

    fraction = 0.0 if body.skip else item_bank_score(item, body)
    existing = await session.scalar(
        select(AttemptAnswer).where(AttemptAnswer.attempt_id == attempt.id, AttemptAnswer.task_id == item.id)
    )
    row = existing or AttemptAnswer(attempt_id=attempt.id, task_id=item.id)
    row.skipped = bool(body.skip)
    row.answer = None if body.skip else body.answer
    row.code = None if body.skip else body.code
    row.language = None if body.skip else body.language
    row.passed = int(round(fraction * 100))
    row.total = 100
    row.verdict = "OK" if fraction >= cat_engine.SOLVE_THRESHOLD else "WRONG_ANSWER"
    row.updated_at = datetime.now(UTC)
    session.add(row)

    used = list(state.get("used") or [])
    used.append(item.id)
    correct = dict(state.get("correct") or {})
    correct[item.id] = fraction
    items = items_for(attempt.specialization)
    theta, se = cat_engine.eap(_responses(items, correct))
    state["used"] = used
    state["correct"] = correct
    state["theta"] = theta
    state["se"] = se
    n = len(used)
    done = False
    if state.get("phase") == "border":
        left = int(state.get("border_left") or 0) - 1
        state["border_left"] = left
        if left <= 0 or not cat_engine.in_border(theta, se) or n >= cat_engine.MAX_LEN + cat_engine.BORDER_EXTRA:
            done = True
    elif n >= cat_engine.MAX_LEN or cat_engine.should_stop(n, se):
        if cat_engine.in_border(theta, se) and n < cat_engine.MAX_LEN + cat_engine.BORDER_EXTRA:
            state["phase"] = "border"
        else:
            done = True

    if done:
        state["current"] = None
        state["phase"] = "done"
        _write(attempt, state)
        return attempt, True

    shown, tests = await _exposure(session, [row_item.id for row_item in items])
    nxt = _pick(items, state, shown, tests)
    state["current"] = nxt.id if nxt else None
    if nxt is None:
        state["phase"] = "done"
        _write(attempt, state)
        return attempt, True
    _write(attempt, state)
    await session.commit()
    return attempt, False


def item_bank_score(item: PlayableItem, body: AnswerIn) -> float:
    from app.assessment.item_bank import score_response

    return score_response(item, answer=body.answer, code=body.code, skipped=False)


async def close(
    session: AsyncSession,
    attempt: Attempt,
    apply_result,
    *,
    current_grade: str | None,
) -> AttemptResult:
    state = _state(attempt)
    items = items_for(attempt.specialization)
    correct = {str(key): float(value) for key, value in (state.get("correct") or {}).items()}
    if correct:
        theta, se = cat_engine.eap(_responses(items, correct))
    else:
        theta, se = cat_engine.prior_eap(attempt.declared_grade)
    state["theta"] = theta
    state["se"] = se
    decision = cat_engine.decide_grade(
        theta,
        se,
        attempt.declared_grade,
        current_grade,
        grade_change=attempt.grade_change,
    )
    score = cat_engine.theta_to_score(theta)
    skills = _skill_scores(items, correct)
    state["decision"] = decision.decision
    state["measured_grade"] = decision.measured
    state["percentile"] = cat_engine.theta_to_percentile(theta)
    state["message"] = decision.message
    state["current"] = None
    state["phase"] = "done"
    _write(attempt, state)
    await _commit_exposure(session, list(state.get("used") or []))
    changed_at = datetime.now(UTC) if attempt.grade_change else None
    result = await apply_result(
        session,
        attempt,
        score=score,
        grade=decision.assigned,
        ready=decision.ready_for_next,
        skill_scores=skills,
        changed_at=changed_at,
    )
    result.theta = theta
    result.se = se
    result.decision = decision.decision
    result.measured_grade = decision.measured  # type: ignore[assignment]
    result.percentile = cat_engine.theta_to_percentile(theta)
    result.message = decision.message
    return result
