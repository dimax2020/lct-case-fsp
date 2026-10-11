"""Taskiq parse task. Registered on app.tasks.broker when this module is imported."""

from uuid import UUID

from app.resume.service import parse_resume_body
from app.tasks import broker


@broker.task
async def parse_resume(resume_id: str) -> None:
    await parse_resume_body(UUID(resume_id))
