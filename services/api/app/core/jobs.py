import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Job


async def create_job(session: AsyncSession, kind: str, payload: dict | None = None) -> Job:
    job = Job(kind=kind, status="queued", payload=payload or {})
    session.add(job)
    await session.flush()
    return job


async def set_job_status(
    session: AsyncSession,
    job_id: uuid.UUID,
    status: str,
    result: dict | None = None,
    error: str | None = None,
) -> Job | None:
    job = await session.get(Job, job_id)
    if job is None:
        return None
    job.status = status
    if result is not None:
        job.result = result
    if error is not None:
        job.error = error
    await session.flush()
    return job


async def get_job(session: AsyncSession, job_id: uuid.UUID) -> Job | None:
    result = await session.execute(select(Job).where(Job.id == job_id))
    return result.scalar_one_or_none()
