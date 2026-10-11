"""Create the local user on first authenticated request.

Profile and company modules register hooks at startup. Auth calls provision_user
after the JWT is accepted. Import this module from inside get_principal, not
at the top of app.core.auth.
"""

from collections.abc import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.core.models import User

Hook = Callable[[AsyncSession, User], Awaitable[None]]

_candidate_hook: Hook | None = None
_company_hook: Hook | None = None


def set_candidate_hook(fn: Hook) -> None:
    global _candidate_hook
    _candidate_hook = fn


def set_company_hook(fn: Hook) -> None:
    global _company_hook
    _company_hook = fn


async def provision_user(session: AsyncSession, principal: Principal) -> User:
    found = await session.execute(select(User).where(User.kc_sub == principal.sub))
    user = found.scalar_one_or_none()
    if user is None:
        user = User(kc_sub=principal.sub, role=principal.role, email=principal.email)
        session.add(user)
        await session.flush()
    elif principal.email and user.email != principal.email:
        user.email = principal.email
    if user.role == "candidate" and _candidate_hook is not None:
        await _candidate_hook(session, user)
    if user.role == "employer" and _company_hook is not None:
        await _company_hook(session, user)
    return user
