"""Candidate and employer hints. Agent D implements §7. Stubs keep callers unblocked."""

from uuid import UUID


async def recompute_candidate(candidate_id: UUID) -> list[dict]:
    del candidate_id
    return []


async def recompute_employer(need_id: UUID) -> list[dict]:
    del need_id
    return []
