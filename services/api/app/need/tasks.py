"""Shortlist job.

Registered on the shared broker when ``app.tasks`` imports this module.
``app.tasks`` keeps a single side-effect import: ``import app.need.tasks``.
"""

from app.need.service import execute_match
from app.tasks import broker


@broker.task(task_name="need.match")
async def match_need_task(need_id: str, job_id: str) -> None:
    await execute_match(need_id, job_id)
