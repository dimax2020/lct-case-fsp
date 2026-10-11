"""`python -m app.demo.seed` and `make seed`.

`--if-empty` загружает демо-данные, только если в базе ещё нет кандидатов: так контейнер
при старте наполняет чистую базу и не трогает уже идущую демонстрацию.
"""

import asyncio
import sys

from sqlalchemy import text

from app.core.db import SessionLocal
from app.demo.service import reseed


async def has_candidates() -> bool:
    async with SessionLocal() as session:
        return bool((await session.execute(text("SELECT EXISTS (SELECT 1 FROM candidates)"))).scalar())


def main() -> None:
    if "--if-empty" in sys.argv[1:] and asyncio.run(has_candidates()):
        print("seed skipped: candidates already present")
        return
    counts = asyncio.run(reseed())
    print(
        "seeded "
        f"candidates={counts['candidates']} companies={counts['companies']} "
        f"needs={counts['needs']} invitations={counts['invitations']}"
    )


if __name__ == "__main__":
    main()
