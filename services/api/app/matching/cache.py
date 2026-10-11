"""Redis shortlist cache. The shortlist key is the need id, TTL from config."""

import json
import logging
from typing import Any
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.settings import get_settings
from app.matching.config import CACHE_TTL_SECONDS

logger = logging.getLogger(__name__)

_REDIS_ERRORS = (RedisError, OSError, ConnectionError, TimeoutError)


def shortlist_key(need_id: UUID | str) -> str:
    return str(need_id)


def employer_hint_key(need_id: UUID | str) -> str:
    return f"hint-e:{need_id}"


def candidate_hint_key(candidate_id: UUID | str) -> str:
    return f"hint-c:{candidate_id}"


def _member_key(candidate_id: str) -> str:
    return f"hint-m:{candidate_id}"


def _client() -> Redis:
    return Redis.from_url(get_settings().redis_url, decode_responses=True)


async def _close(client: Redis | None) -> None:
    if client is not None:
        await client.aclose()


async def cache_get(need_id: UUID) -> dict[str, Any] | None:
    client: Redis | None = None
    try:
        client = _client()
        raw = await client.get(shortlist_key(need_id))
    except _REDIS_ERRORS:
        logger.warning("shortlist cache read failed", exc_info=True)
        return None
    finally:
        await _close(client)
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


async def cache_set(need_id: UUID, payload: dict[str, Any]) -> None:
    raw = json.dumps(payload, ensure_ascii=False)
    client: Redis | None = None
    try:
        client = _client()
        await client.set(shortlist_key(need_id), raw, ex=CACHE_TTL_SECONDS)
        await client.delete(employer_hint_key(need_id))
        await _remember_members(client, need_id, payload)
    except _REDIS_ERRORS:
        logger.warning("shortlist cache write failed", exc_info=True)
    finally:
        await _close(client)


async def _remember_members(client: Redis, need_id: UUID, payload: dict[str, Any]) -> None:
    need = str(need_id)
    for row in payload.get("rows") or []:
        if not isinstance(row, dict):
            continue
        candidate_id = row.get("candidate_id")
        if not candidate_id:
            continue
        key = _member_key(str(candidate_id))
        await client.sadd(key, need)
        await client.expire(key, CACHE_TTL_SECONDS)


async def invalidate(need_id: UUID) -> None:
    client: Redis | None = None
    try:
        client = _client()
        await client.delete(shortlist_key(need_id), employer_hint_key(need_id))
    except _REDIS_ERRORS:
        logger.warning("shortlist cache delete failed", exc_info=True)
    finally:
        await _close(client)


async def invalidate_candidate(candidate_id: UUID) -> None:
    client: Redis | None = None
    try:
        client = _client()
        member = _member_key(str(candidate_id))
        raw_ids = await client.smembers(member)
        need_ids = [item.decode() if isinstance(item, bytes) else str(item) for item in raw_ids]
        keys = [shortlist_key(need_id) for need_id in need_ids]
        keys.extend(employer_hint_key(need_id) for need_id in need_ids)
        keys.append(candidate_hint_key(candidate_id))
        keys.append(member)
        if keys:
            await client.delete(*keys)
    except _REDIS_ERRORS:
        logger.warning("candidate cache delete failed", exc_info=True)
    finally:
        await _close(client)


async def hints_get(key: str) -> list[dict[str, Any]] | None:
    client: Redis | None = None
    try:
        client = _client()
        raw = await client.get(key)
    except _REDIS_ERRORS:
        return None
    finally:
        await _close(client)
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, list):
        return None
    return [item for item in payload if isinstance(item, dict)]


async def hints_set(key: str, hints: list[dict[str, Any]]) -> None:
    raw = json.dumps(hints, ensure_ascii=False)
    client: Redis | None = None
    try:
        client = _client()
        await client.set(key, raw, ex=CACHE_TTL_SECONDS)
    except _REDIS_ERRORS:
        logger.warning("hint cache write failed", exc_info=True)
    finally:
        await _close(client)
