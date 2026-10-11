"""Idempotent reseed.

Module services do not persist yet (no upsert on profile, company, need or
invitation). ``app.demo.load`` writes the committed JSON with SQL text so this
package does not import their models. See that module for the blocker.
"""

from app.demo.load import load_seed


async def reseed() -> dict[str, int]:
    return await load_seed()
