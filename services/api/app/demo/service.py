"""Idempotent seed goes through module services, not raw SQL. Agent G implements it."""


async def reseed() -> dict[str, int]:
    return {"candidates": 0, "companies": 0, "needs": 0, "invitations": 0}
