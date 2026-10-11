"""JWT principal.

get_principal(request) -> Principal stays the phase-0 signature. A valid access
token is checked against the Keycloak JWKS (10 minute cache), iss, aud, and exp.
The business role is the realm role candidate, employer, or admin.

provision_user is imported inside get_principal so this module does not cycle
with app.core.provision at import time.
"""

import os
import time
from dataclasses import dataclass
from typing import Any

import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientError
from starlette.requests import Request

from app.core.errors import AppError
from app.core.settings import get_settings

_BUSINESS_ROLES = ("admin", "employer", "candidate")
_JWKS_CACHE_SECONDS = 600
_jwks_clients: dict[str, tuple[float, PyJWKClient]] = {}


@dataclass(frozen=True)
class Principal:
    sub: str
    role: str
    email: str | None = None


def clear_jwks_cache() -> None:
    _jwks_clients.clear()


def _unauthorized() -> AppError:
    return AppError("unauthorized", "Нужна авторизация", status_code=401)


def _jwks_url() -> str:
    override = os.environ.get("KEYCLOAK_JWKS_URL", "").strip()
    if override:
        return override
    return f"{get_settings().keycloak_issuer.rstrip('/')}/protocol/openid-connect/certs"


def _jwks_client() -> PyJWKClient:
    url = _jwks_url()
    now = time.monotonic()
    cached = _jwks_clients.get(url)
    if cached is not None and now - cached[0] < _JWKS_CACHE_SECONDS:
        return cached[1]
    client = PyJWKClient(url, cache_keys=True, lifespan=_JWKS_CACHE_SECONDS)
    _jwks_clients[url] = (now, client)
    return client


def _bearer(request: Request) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise _unauthorized()
    return token.strip()


def _role_from_claims(claims: dict[str, Any]) -> str:
    realm = claims.get("realm_access")
    roles = realm.get("roles") if isinstance(realm, dict) else None
    if not isinstance(roles, list):
        return ""
    for role in _BUSINESS_ROLES:
        if role in roles:
            return role
    return ""


def _claims(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        decoded = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.keycloak_client_id,
            issuer=settings.keycloak_issuer,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except (jwt.PyJWTError, PyJWKClientError, ValueError):
        raise _unauthorized() from None
    if not isinstance(decoded, dict):
        raise _unauthorized()
    return decoded


async def get_principal(request: Request) -> Principal:
    claims = _claims(_bearer(request))
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        raise _unauthorized()
    email = claims.get("email")
    principal = Principal(
        sub=sub,
        role=_role_from_claims(claims),
        email=email if isinstance(email, str) else None,
    )
    if principal.role in _BUSINESS_ROLES:
        from app.core.db import SessionLocal
        from app.core.provision import provision_user

        async with SessionLocal() as session:
            await provision_user(session, principal)
            await session.commit()
    return principal


def require_role(*roles: str):  # type: ignore[no-untyped-def]
    from fastapi import Depends

    async def _dependency(principal: Principal = Depends(get_principal)) -> Principal:
        if principal.role not in roles:
            raise AppError("forbidden", "Недостаточно прав", status_code=403)
        return principal

    return _dependency
