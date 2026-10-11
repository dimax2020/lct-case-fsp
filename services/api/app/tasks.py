"""Taskiq broker shared by the API and the worker."""

from taskiq_redis import ListQueueBroker

from app.core.settings import get_settings

broker = ListQueueBroker(get_settings().redis_url)


@broker.task
async def ping() -> str:
    return "ok"


def _register_need_tasks() -> None:
    # Side-effect import: app.need.tasks registers match_need_task on this broker.
    import app.need.tasks as need_tasks

    _ = need_tasks


_register_need_tasks()
