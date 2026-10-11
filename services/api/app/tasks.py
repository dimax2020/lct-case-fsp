"""Taskiq broker shared by the API and the worker."""

from taskiq_redis import ListQueueBroker

from app.core.settings import get_settings

broker = ListQueueBroker(get_settings().redis_url)


@broker.task
async def ping() -> str:
    return "ok"
