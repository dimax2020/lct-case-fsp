"""Short employer tasks that keep a candidate profile fresh. Not a second test engine."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment.item_bank import micro_tasks as bank_micro_tasks
from app.assessment.models import MicroAnswer, MicroTask
from app.assessment.schemas import MicroAnswerIn, MicroAnswerOut, MicroTaskCreate, MicroTaskOut
from app.assessment.service import ensure_candidate_id
from app.core.auth import Principal
from app.core.errors import AppError

BUILTIN_MICRO_TASKS: tuple[tuple[str, str], ...] = (
    (
        "Разберите гонку в кэше",
        "Коротко разберите гонку при чтении и записи кэша и чем её закрыть.",
    ),
    (
        "Как бы вы деградировали Kafka-консьюмер",
        "Коротко опишите, как снизить нагрузку Kafka-консьюмера и не потерять сообщения.",
    ),
)


def _out(row: MicroTask) -> MicroTaskOut:
    return MicroTaskOut(id=row.id, title=row.title, body=row.body, need_id=row.need_id)


async def _ensure_builtin(session: AsyncSession) -> None:
    await session.execute(text("LOCK TABLE micro_tasks IN EXCLUSIVE MODE"))
    total = await session.scalar(select(func.count()).select_from(MicroTask))
    if total:
        return
    now = datetime.now(UTC)
    seeded = list(BUILTIN_MICRO_TASKS)
    for item in bank_micro_tasks():
        pair = (item["title"], item["body"])
        if pair not in seeded:
            seeded.append(pair)
    for index, (title, body) in enumerate(seeded):
        session.add(
            MicroTask(
                title=title,
                body=body,
                is_open=True,
                created_at=now + timedelta(microseconds=index),
            )
        )
    await session.commit()


async def list_micro_tasks(session: AsyncSession, principal: Principal) -> list[MicroTaskOut]:
    candidate_id = await ensure_candidate_id(session, principal)
    await _ensure_builtin(session)
    rows = await session.scalars(
        select(MicroTask)
        .outerjoin(
            MicroAnswer,
            and_(MicroAnswer.task_id == MicroTask.id, MicroAnswer.candidate_id == candidate_id),
        )
        .where(MicroTask.is_open.is_(True), MicroAnswer.id.is_(None))
        .order_by(MicroTask.created_at, MicroTask.title)
    )
    return [_out(row) for row in rows.all()]


async def create_micro_task(session: AsyncSession, body: MicroTaskCreate) -> MicroTaskOut:
    if body.need_id is not None:
        found = await session.execute(
            text("SELECT 1 FROM needs WHERE id = CAST(:id AS uuid)"),
            {"id": str(body.need_id)},
        )
        if found.scalar_one_or_none() is None:
            raise AppError("need_not_found", "Потребность не найдена", status_code=404)
    row = MicroTask(
        title=body.title,
        body=body.body,
        need_id=body.need_id,
        is_open=True,
        created_at=datetime.now(UTC),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _out(row)


async def answer_micro_task(
    session: AsyncSession,
    principal: Principal,
    task_id: UUID,
    body: MicroAnswerIn,
) -> MicroAnswerOut:
    candidate_id = await ensure_candidate_id(session, principal)
    task = await session.get(MicroTask, task_id)
    if task is None or not task.is_open:
        raise AppError("micro_not_found", "Задание не найдено", status_code=404)
    existing = await session.scalar(
        select(MicroAnswer.id).where(MicroAnswer.task_id == task.id, MicroAnswer.candidate_id == candidate_id)
    )
    if existing is not None:
        raise AppError("micro_answered", "Ответ уже отправлен", status_code=409)
    row = MicroAnswer(task_id=task.id, candidate_id=candidate_id, answer=body.answer)
    session.add(row)
    await session.execute(
        text("UPDATE candidates SET last_active_at = :now WHERE id = CAST(:id AS uuid)"),
        {"now": datetime.now(UTC), "id": str(candidate_id)},
    )
    await session.commit()
    await session.refresh(row)
    return MicroAnswerOut(id=row.id, task_id=row.task_id, answer=row.answer)
