"""Periodic expiry of invitations that are past their reply deadline."""

from sqlalchemy.ext.asyncio import AsyncSession
from taskiq import TaskiqScheduler
from taskiq.schedule_sources import LabelScheduleSource

from app.core.db import SessionLocal
from app.invitation.service import expire_due
from app.tasks import broker


async def expire_overdue(session: AsyncSession | None = None) -> int:
    if session is not None:
        return await expire_due(session)
    async with SessionLocal() as owned:
        return await expire_due(owned)


@broker.task(schedule=[{"cron": "*/5 * * * *", "schedule_id": "expire_overdue_invitations"}])
async def expire_overdue_invitations() -> int:
    return await expire_overdue()


scheduler = TaskiqScheduler(broker=broker, sources=[LabelScheduleSource(broker)])
