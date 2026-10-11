"""Create the local user on first authenticated request.

Profile and company modules register hooks at startup. Auth calls provision_user
after the JWT is accepted. Import this module from inside get_principal, not
at the top of app.core.auth.
"""

from collections.abc import Awaitable, Callable
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.core.models import User

Hook = Callable[[AsyncSession, User], Awaitable[None]]
AttachDecision = Literal["use_sub", "attach_email", "create"]

_candidate_hook: Hook | None = None
_company_hook: Hook | None = None


def set_candidate_hook(fn: Hook) -> None:
    global _candidate_hook
    _candidate_hook = fn


def set_company_hook(fn: Hook) -> None:
    global _company_hook
    _company_hook = fn


def email_attach_decision(matched_by_sub: bool, email: str | None, matched_by_email: bool) -> AttachDecision:
    """Choose how the first login binds a Keycloak principal to a users row.

    Seed rows are stored as kc_sub ``seed:<email>``. When that sub is absent and
    the principal has an email that already exists, reuse the row instead of
    inserting a duplicate.
    """
    if matched_by_sub:
        return "use_sub"
    if email is not None and email.strip() and matched_by_email:
        return "attach_email"
    return "create"


async def user_by_email(session: AsyncSession, email: str | None) -> User | None:
    if email is None or not email.strip():
        return None
    normalized = email.strip().lower()
    rows = list(await session.scalars(select(User).where(func.lower(User.email) == normalized)))
    if not rows:
        return None
    seed_sub = f"seed:{normalized}"
    for row in rows:
        if row.kc_sub.lower() == seed_sub:
            return row
    for row in rows:
        if row.kc_sub.startswith("seed:"):
            return row
    return rows[0]


async def provision_user(session: AsyncSession, principal: Principal) -> User:
    found = await session.execute(select(User).where(User.kc_sub == principal.sub))
    user = found.scalar_one_or_none()
    if user is None:
        email_user = await user_by_email(session, principal.email)
        decision = email_attach_decision(False, principal.email, email_user is not None)
        if decision == "attach_email" and email_user is not None:
            email_user.kc_sub = principal.sub
            if principal.email and email_user.email != principal.email:
                email_user.email = principal.email
            user = email_user
        else:
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
