"""`python -m app.demo.seed` and `make seed`."""

import asyncio

from app.demo.service import reseed


def main() -> None:
    counts = asyncio.run(reseed())
    print(
        "seeded "
        f"candidates={counts['candidates']} companies={counts['companies']} "
        f"needs={counts['needs']} invitations={counts['invitations']}"
    )


if __name__ == "__main__":
    main()
