"""Candidate and employer hints. Numbers come from the same filters as the shortlist."""

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import InterfaceError, OperationalError

import app.matching.service as matching
from app.core.auth import Principal
from app.core.db import SessionLocal
from app.profile.service import CandidateFeatures

logger = logging.getLogger(__name__)

_CONNECTION_ERRORS = (OperationalError, InterfaceError, OSError, ConnectionError, TimeoutError)


async def recompute_candidate(candidate_id: UUID) -> list[dict[str, Any]]:
    try:
        return await matching.recompute_candidate(candidate_id)
    except _CONNECTION_ERRORS:
        logger.warning("candidate hints skipped, store is unreachable", exc_info=True)
        return []


async def recompute_employer(need_id: UUID) -> list[dict[str, Any]]:
    try:
        return await matching.recompute_employer(need_id)
    except _CONNECTION_ERRORS:
        logger.warning("employer hints skipped, store is unreachable", exc_info=True)
        return []


def build_candidate_hints(
    candidate: CandidateFeatures,
    needs: list[Any],
    peers: list[CandidateFeatures] | None = None,
    today: Any = None,
) -> list[dict[str, Any]]:
    return matching.build_candidate_hints(candidate, needs, peers, today=today)


def build_employer_hints(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return matching.build_employer_hints(payload)


def apply_employer_hint(payload: dict[str, Any], hint: dict[str, Any]) -> list[dict[str, Any]]:
    return matching.apply_employer_hint(payload, hint)


async def require_employer_need(session: Any, principal: Principal, need_id: UUID) -> None:
    import importlib

    module = importlib.import_module("app.need.service")
    await module.require_need(session, principal, need_id)


async def candidate_id_for(principal: Principal) -> UUID | None:
    try:
        async with SessionLocal() as session:
            result = await session.execute(
                text(
                    """
                    SELECT c.id
                    FROM candidates c
                    JOIN users u ON u.id = c.user_id
                    WHERE u.kc_sub = :sub
                    """
                ),
                {"sub": principal.sub},
            )
            return result.scalar_one_or_none()
    except _CONNECTION_ERRORS:
        logger.warning("candidate lookup skipped", exc_info=True)
        return None
