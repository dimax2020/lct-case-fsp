"""Taskiq broker shared by the API and the worker."""

from taskiq_redis import ListQueueBroker

from app.core.settings import get_settings

broker = ListQueueBroker(get_settings().redis_url)


@broker.task
async def ping() -> str:
    return "ok"


def _register_tasks() -> None:
    """Import task modules so `taskiq worker app.tasks:broker` sees them."""
    import app.invitation.tasks as invitation_tasks
    import app.need.tasks as need_tasks
    import app.profile.evidence as profile_evidence
    import app.resume.tasks as resume_tasks

    _ = (invitation_tasks, need_tasks, profile_evidence, resume_tasks)


_register_tasks()
