"""Прохождение теста рабочего стиля и выдача результатов кандидату и работодателю."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.profile.service as profile_api
from app.core.auth import Principal
from app.core.errors import AppError
from app.psych import bank
from app.psych.models import PsychAttempt
from app.psych.schemas import (
    PsychAnswers,
    PsychAttemptOut,
    PsychEmployerView,
    PsychFinishIn,
    PsychProgress,
    PsychState,
)
from app.psych.scoring import candidate_view, clean_answers, progress, score

# Пересдача не чаще раза в 30 дней: ответы на опросник легко «подогнать» повторными попытками.
RETAKE_DAYS = 30


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _attempt_out(row: PsychAttempt) -> PsychAttemptOut:
    answers = clean_answers(row.answers or {})
    return PsychAttemptOut(
        id=row.id,
        version=row.version,
        answers=PsychAnswers.model_validate(answers),
        progress=PsychProgress.model_validate(progress(answers)),
        started_at=_utc(row.started_at),
        finished_at=_utc(row.finished_at) if row.finished_at else None,
    )


async def _open_attempt(session: AsyncSession, candidate_id: UUID) -> PsychAttempt | None:
    return await session.scalar(
        select(PsychAttempt)
        .where(PsychAttempt.candidate_id == candidate_id, PsychAttempt.finished_at.is_(None))
        .order_by(PsychAttempt.started_at.desc())
        .limit(1)
    )


async def _last_finished(session: AsyncSession, candidate_id: UUID) -> PsychAttempt | None:
    return await session.scalar(
        select(PsychAttempt)
        .where(PsychAttempt.candidate_id == candidate_id, PsychAttempt.finished_at.is_not(None))
        .order_by(PsychAttempt.finished_at.desc())
        .limit(1)
    )


def _next_attempt_at(last: PsychAttempt | None) -> datetime | None:
    if last is None or last.finished_at is None:
        return None
    moment = _utc(last.finished_at) + timedelta(days=RETAKE_DAYS)
    return moment if moment > datetime.now(UTC) else None


async def state(session: AsyncSession, candidate: Any) -> PsychState:
    open_row = await _open_attempt(session, candidate.id)
    last = await _last_finished(session, candidate.id)
    next_at = _next_attempt_at(last)
    return PsychState(
        attempt=_attempt_out(open_row) if open_row else None,
        result=candidate_view(last.result) if last and last.result else None,
        finished_at=_utc(last.finished_at) if last and last.finished_at else None,
        can_start=open_row is not None or next_at is None,
        next_attempt_at=next_at,
        share_with_employers=bool(getattr(candidate, "show_psych", False)),
        limitations=list(bank.LIMITATIONS),
    )


async def start(session: AsyncSession, candidate: Any) -> PsychAttemptOut:
    open_row = await _open_attempt(session, candidate.id)
    if open_row is not None:
        return _attempt_out(open_row)
    next_at = _next_attempt_at(await _last_finished(session, candidate.id))
    if next_at is not None:
        raise AppError(
            "retake_too_early",
            f"Пройти тест снова можно с {next_at.astimezone(UTC).strftime('%d.%m.%Y')}",
            status_code=409,
        )
    row = PsychAttempt(candidate_id=candidate.id, version=bank.VERSION, answers={}, started_at=datetime.now(UTC))
    session.add(row)
    await session.flush()
    return _attempt_out(row)


async def _owned_open(session: AsyncSession, candidate: Any, attempt_id: UUID) -> PsychAttempt:
    row = await session.get(PsychAttempt, attempt_id)
    if row is None or row.candidate_id != candidate.id:
        raise AppError("not_found", "Прохождение не найдено", status_code=404)
    if row.finished_at is not None:
        raise AppError("attempt_finished", "Тест уже завершён", status_code=409)
    return row


async def save(session: AsyncSession, candidate: Any, attempt_id: UUID, answers: PsychAnswers) -> PsychAttemptOut:
    row = await _owned_open(session, candidate, attempt_id)
    row.answers = clean_answers(answers.model_dump())
    row.updated_at = datetime.now(UTC)
    await session.flush()
    return _attempt_out(row)


async def finish(session: AsyncSession, candidate: Any, attempt_id: UUID, body: PsychFinishIn) -> PsychState:
    row = await _owned_open(session, candidate, attempt_id)
    if body.answers is not None:
        row.answers = clean_answers(body.answers.model_dump())
    answers = clean_answers(row.answers or {})
    done = progress(answers)
    if done["blocks_done"] == 0 and done["statements_done"] == 0 and done["cases_done"] == 0:
        raise AppError("validation_error", "Ответьте хотя бы на часть вопросов", status_code=422)
    now = datetime.now(UTC)
    duration = (now - _utc(row.started_at)).total_seconds()
    row.result = score(answers, duration_seconds=duration)
    row.finished_at = now
    if body.share_with_employers is not None:
        await profile_api.set_psych_sharing(session, candidate, body.share_with_employers)
    await session.flush()
    return await state(session, candidate)


async def share(session: AsyncSession, candidate: Any, value: bool) -> PsychState:
    await profile_api.set_psych_sharing(session, candidate, value)
    return await state(session, candidate)


async def employer_view(session: AsyncSession, principal: Principal, candidate_id: UUID) -> PsychEmployerView:
    company_id = await profile_api.employer_company_id(session, principal)
    privacy = (await profile_api.privacy_for(session, [candidate_id])).get(candidate_id)
    if privacy is None or not privacy["visible"] or (company_id is not None and company_id in privacy["hidden_company_ids"]):
        raise AppError("not_found", "Кандидат не найден", status_code=404)
    limitations = list(bank.LIMITATIONS)
    if not privacy["show_psych"]:
        return PsychEmployerView(available=False, reason="Кандидат не открыл результаты теста рабочего стиля.",
                                 limitations=limitations)
    last = await _last_finished(session, candidate_id)
    if last is None or not last.result or last.finished_at is None:
        return PsychEmployerView(available=False, reason="Кандидат ещё не проходил тест рабочего стиля.",
                                 limitations=limitations)
    finished = _utc(last.finished_at)
    if finished < datetime.now(UTC) - timedelta(days=bank.RESULT_TTL_DAYS):
        return PsychEmployerView(available=False, reason="Результат старше 12 месяцев и больше не показывается.",
                                 limitations=limitations)
    return PsychEmployerView(available=True, finished_at=finished, result=last.result, limitations=limitations)
