import time
from collections.abc import AsyncIterator

import jwt
import pytest
from app.core.auth import Principal, clear_jwks_cache
from app.core.errors import AppError
from app.core.models import User
from app.core.settings import get_settings
from app.main import app
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient

_PRIVATE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUBLIC = _PRIVATE.public_key()
_OTHER = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _SigningKey:
    def __init__(self, key: object) -> None:
        self.key = key


class _FakeJWKClient:
    built: list[dict[str, object]] = []

    def __init__(self, url: str, **kwargs: object) -> None:
        self.url = url
        _FakeJWKClient.built.append({"url": url, **kwargs})

    def get_signing_key_from_jwt(self, token: str) -> _SigningKey:
        del token
        return _SigningKey(_PUBLIC)


class _Session:
    async def __aenter__(self) -> "_Session":
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False

    async def commit(self) -> None:
        return None


def _token(**overrides: object) -> str:
    settings = get_settings()
    payload: dict[str, object] = {
        "sub": "user-1",
        "iss": settings.keycloak_issuer,
        "aud": settings.keycloak_client_id,
        "exp": int(time.time()) + 600,
        "email": "candidate@demo.fsp",
        "realm_access": {"roles": ["candidate", "default-roles-fsp"]},
    }
    payload.update(overrides)
    return jwt.encode(payload, _PRIVATE, algorithm="RS256")


@pytest.fixture
async def provisioned(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[list[Principal]]:
    calls: list[Principal] = []

    async def fake_provision(_session: object, principal: Principal) -> User:
        calls.append(principal)
        return User(kc_sub=principal.sub, role=principal.role, email=principal.email)

    async def stop_after_auth(_session: object, _user_id: object) -> None:
        raise AppError("not_implemented", "Метод ещё не реализован", status_code=501)

    _FakeJWKClient.built = []
    clear_jwks_cache()
    monkeypatch.setattr("app.core.auth.PyJWKClient", _FakeJWKClient)
    monkeypatch.setattr("app.core.provision.provision_user", fake_provision)
    monkeypatch.setattr("app.profile.storage.provision_user", fake_provision)
    monkeypatch.setattr("app.profile.storage.get_or_create_candidate", stop_after_auth)
    monkeypatch.setattr("app.core.db.SessionLocal", lambda: _Session())
    yield calls
    clear_jwks_cache()


@pytest.fixture
async def client(provisioned: list[Principal]) -> AsyncIterator[AsyncClient]:
    del provisioned
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


async def test_health_does_not_require_a_token(client: AsyncClient) -> None:
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_missing_token_is_401(client: AsyncClient, provisioned: list[Principal]) -> None:
    response = await client.get("/api/v1/candidates/me")
    assert response.status_code == 401
    body = response.json()
    assert set(body["error"]) >= {"code", "message"}
    assert body["error"]["code"] == "unauthorized"
    assert provisioned == []


async def test_invalid_token_is_401(client: AsyncClient, provisioned: list[Principal]) -> None:
    response = await client.get("/api/v1/candidates/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
    assert provisioned == []


async def test_wrong_signature_is_401(client: AsyncClient) -> None:
    token = jwt.encode({"sub": "x", "exp": int(time.time()) + 60}, _OTHER, algorithm="RS256")
    response = await client.get("/api/v1/candidates/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


async def test_expired_wrong_issuer_and_audience_are_401(client: AsyncClient) -> None:
    settings = get_settings()
    expired = _token(exp=int(time.time()) - 30)
    wrong_iss = _token(iss="http://evil.example/realms/fsp")
    wrong_aud = _token(aud="account")
    for token in (expired, wrong_iss, wrong_aud):
        response = await client.get("/api/v1/candidates/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401, token
    listed = _token(aud=[settings.keycloak_client_id, "account"])
    response = await client.get("/api/v1/candidates/me", headers={"Authorization": f"Bearer {listed}"})
    assert response.status_code == 501


async def test_wrong_role_is_403(client: AsyncClient, provisioned: list[Principal]) -> None:
    token = _token(realm_access={"roles": ["candidate"]})
    response = await client.get("/api/v1/companies/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    assert provisioned[0].role == "candidate"


async def test_token_without_business_role_is_403_and_does_not_provision(
    client: AsyncClient, provisioned: list[Principal]
) -> None:
    token = _token(realm_access={"roles": ["default-roles-fsp"]})
    response = await client.get("/api/v1/candidates/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    assert provisioned == []


async def test_valid_token_provisions_user(client: AsyncClient, provisioned: list[Principal]) -> None:
    token = _token(sub="kc-sub-1", email="candidate@demo.fsp")
    response = await client.get("/api/v1/candidates/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 501
    assert response.json()["error"]["code"] == "not_implemented"
    assert Principal(sub="kc-sub-1", role="candidate", email="candidate@demo.fsp") in provisioned


async def test_jwks_client_is_cached_for_ten_minutes(client: AsyncClient) -> None:
    token = _token()
    await client.get("/api/v1/candidates/me", headers={"Authorization": f"Bearer {token}"})
    await client.get("/api/v1/candidates/me", headers={"Authorization": f"Bearer {token}"})
    assert len(_FakeJWKClient.built) == 1
    assert _FakeJWKClient.built[0]["cache_keys"] is True
    assert _FakeJWKClient.built[0]["lifespan"] == 600

