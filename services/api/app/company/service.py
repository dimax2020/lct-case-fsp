"""Company profile. Agent E implements persistence."""

from uuid import UUID


async def ensure_company(user_id: UUID) -> UUID:
    return user_id
