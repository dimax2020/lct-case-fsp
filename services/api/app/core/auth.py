"""JWT principal.

Phase 0 returns a debug principal. Agent A replaces the body of get_principal
and keeps this signature. Optional email does not break Principal(sub, role).

Role for a newly registered user is not in the token until the BFF assigns a
realm role (see infra/keycloak/realm-export.json). Do not import
app.core.provision at module level — call it inside get_principal after the
token is valid, so this module stays free of a cycle.
"""

from dataclasses import dataclass

from starlette.requests import Request


@dataclass(frozen=True)
class Principal:
    sub: str
    role: str
    email: str | None = None


async def get_principal(request: Request) -> Principal:
    role = request.headers.get("x-debug-role", "candidate")
    sub = request.headers.get("x-debug-sub", "stub-candidate")
    email = request.headers.get("x-debug-email")
    if role not in {"candidate", "employer", "admin"}:
        role = "candidate"
    return Principal(sub=sub, role=role, email=email)


def require_role(*roles: str):  # type: ignore[no-untyped-def]
    from fastapi import Depends

    from app.core.errors import AppError

    async def _dependency(principal: Principal = Depends(get_principal)) -> Principal:
        if principal.role not in roles:
            raise AppError("forbidden", "Недостаточно прав", status_code=403)
        return principal

    return _dependency
