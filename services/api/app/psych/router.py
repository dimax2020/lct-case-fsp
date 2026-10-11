from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

import app.psych.service as psych
from app.core.auth import Principal, require_role
from app.profile.service import current_candidate, get_db
from app.psych.bank import public_test
from app.psych.schemas import (
    PsychAnswers,
    PsychAttemptOut,
    PsychEmployerView,
    PsychFinishIn,
    PsychShareIn,
    PsychState,
    PsychTest,
)

router = APIRouter(tags=["psych"])


async def _db() -> AsyncIterator[AsyncSession]:
    async for session in get_db():
        yield session


@router.get("/psych/test", response_model=PsychTest)
async def get_psych_test(_: Principal = Depends(require_role("candidate"))) -> PsychTest:
    """Вопросы трёх частей теста без ключа подсчёта."""
    return PsychTest.model_validate(public_test())


@router.get("/psych/me", response_model=PsychState)
async def get_my_psych(
    principal: Principal = Depends(require_role("candidate")),
    session: AsyncSession = Depends(_db),
) -> PsychState:
    candidate = await current_candidate(session, principal)
    return await psych.state(session, candidate)


@router.post("/psych/attempts", response_model=PsychAttemptOut, status_code=201)
async def start_psych_attempt(
    principal: Principal = Depends(require_role("candidate")),
    session: AsyncSession = Depends(_db),
) -> PsychAttemptOut:
    """Начать тест или вернуть незавершённое прохождение. 409 — пересдача раньше срока."""
    candidate = await current_candidate(session, principal)
    return await psych.start(session, candidate)


@router.put("/psych/attempts/{id}", response_model=PsychAttemptOut)
async def save_psych_attempt(
    id: UUID,
    body: PsychAnswers,
    principal: Principal = Depends(require_role("candidate")),
    session: AsyncSession = Depends(_db),
) -> PsychAttemptOut:
    """Сохранить черновик ответов: прогресс переживает перезагрузку страницы."""
    candidate = await current_candidate(session, principal)
    return await psych.save(session, candidate, id, body)


@router.post("/psych/attempts/{id}/finish", response_model=PsychState)
async def finish_psych_attempt(
    id: UUID,
    body: PsychFinishIn,
    principal: Principal = Depends(require_role("candidate")),
    session: AsyncSession = Depends(_db),
) -> PsychState:
    candidate = await current_candidate(session, principal)
    return await psych.finish(session, candidate, id, body)


@router.put("/psych/me/share", response_model=PsychState)
async def share_my_psych(
    body: PsychShareIn,
    principal: Principal = Depends(require_role("candidate")),
    session: AsyncSession = Depends(_db),
) -> PsychState:
    """Открыть или закрыть результаты для работодателей."""
    candidate = await current_candidate(session, principal)
    return await psych.share(session, candidate, body.share_with_employers)


@router.get("/psych/candidates/{candidate_id}", response_model=PsychEmployerView)
async def get_candidate_psych(
    candidate_id: UUID,
    principal: Principal = Depends(require_role("employer")),
    session: AsyncSession = Depends(_db),
) -> PsychEmployerView:
    """Результат кандидата для работодателя — только с согласия кандидата и не старше 12 месяцев."""
    return await psych.employer_view(session, principal, candidate_id)
