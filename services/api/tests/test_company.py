import os
import socket
import subprocess
import time
from collections.abc import AsyncIterator

import pytest
from app.assessment import models as assessment_models  # noqa: F401
from app.chat import models as chat_models  # noqa: F401
from app.company.models import Company
from app.core.auth import Principal, get_principal
from app.core.db import Base, get_session
from app.core.provision import provision_user
from app.invitation import models as invitation_models  # noqa: F401
from app.main import app
from app.need import models as need_models  # noqa: F401
from app.profile import models as profile_models  # noqa: F401
from app.resume import models as resume_models  # noqa: F401
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.requests import Request

DSN = os.environ.get("FSP_TEST_DSN", "postgresql+asyncpg://fsp:fsp@127.0.0.1:54329/fsp_agent_e")


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.3):
            return True
    except OSError:
        return False


def ensure_test_postgres() -> str:
    if os.environ.get("FSP_TEST_DSN"):
        return DSN
    if _port_open("127.0.0.1", 54329):
        return DSN
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            "fsp-agent-e-pg",
            "-e",
            "POSTGRES_USER=fsp",
            "-e",
            "POSTGRES_PASSWORD=fsp",
            "-e",
            "POSTGRES_DB=fsp_agent_e",
            "-p",
            "127.0.0.1:54329:5432",
            "pgvector/pgvector:pg16",
        ],
        check=False,
        capture_output=True,
    )
    subprocess.run(["docker", "start", "fsp-agent-e-pg"], check=False, capture_output=True)
    for _ in range(50):
        if _port_open("127.0.0.1", 54329):
            return DSN
        time.sleep(0.2)
    raise RuntimeError("test postgres is not available on 127.0.0.1:54329")


async def debug_principal(request: Request) -> Principal:
    role = request.headers.get("x-debug-role", "candidate")
    sub = request.headers.get("x-debug-sub", "stub-candidate")
    email = request.headers.get("x-debug-email")
    if role not in {"candidate", "employer", "admin"}:
        role = "candidate"
    return Principal(sub=sub, role=role, email=email)


@pytest.fixture
async def api() -> AsyncIterator[tuple[AsyncClient, async_sessionmaker[AsyncSession]]]:
    engine = create_async_engine(ensure_test_postgres(), pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    async with factory() as session:
        names = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
        await session.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
        await session.commit()

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_principal] = debug_principal
    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            yield client, factory
        finally:
            app.dependency_overrides.clear()
    await engine.dispose()


PROFILE = {
    "name": "ФСП Лаб",
    "city": "Новосибирск",
    "size": "51-200",
    "industry": "финтех",
    "about": "Делаем карьерный сервис для студентов.",
    "recruiter_contact": {"name": "Ирина", "email": "hr@company.test", "phone": "+79000000001"},
    "benefits": ["dms", "accreditation", "flexible_start"],
}


async def test_candidate_cannot_read_company(api: tuple[AsyncClient, async_sessionmaker[AsyncSession]]) -> None:
    client, _factory = api
    response = await client.get("/api/v1/companies/me", headers={"x-debug-role": "candidate", "x-debug-sub": "can-1"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_first_employer_login_creates_one_company(
    api: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, factory = api
    headers = {"x-debug-role": "employer", "x-debug-sub": "emp-1", "x-debug-email": "boss@lab.test"}
    first = await client.get("/api/v1/companies/me", headers=headers)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["name"] == ""
    assert body["benefits"] == []
    assert body["recruiter_contact"]["email"] is None
    second = await client.get("/api/v1/companies/me", headers=headers)
    assert second.status_code == 200
    assert second.json()["id"] == body["id"]
    async with factory() as session:
        rows = list(await session.scalars(select(Company)))
    assert len(rows) == 1
    assert rows[0].owner_user_id is not None


async def test_company_profile_roundtrip(api: tuple[AsyncClient, async_sessionmaker[AsyncSession]]) -> None:
    client, _factory = api
    headers = {"x-debug-role": "employer", "x-debug-sub": "emp-1", "x-debug-email": "boss@lab.test"}
    saved = await client.put("/api/v1/companies/me", headers=headers, json=PROFILE)
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["name"] == "ФСП Лаб"
    assert body["city"] == "Новосибирск"
    assert body["size"] == "51-200"
    assert body["industry"] == "финтех"
    assert body["about"] == PROFILE["about"]
    assert body["recruiter_contact"] == PROFILE["recruiter_contact"]
    assert body["benefits"] == ["dms", "accreditation", "flexible_start"]
    loaded = await client.get("/api/v1/companies/me", headers=headers)
    assert loaded.status_code == 200
    assert loaded.json() == body


async def test_employers_get_separate_companies(api: tuple[AsyncClient, async_sessionmaker[AsyncSession]]) -> None:
    client, _factory = api
    first = await client.get("/api/v1/companies/me", headers={"x-debug-role": "employer", "x-debug-sub": "emp-a"})
    second = await client.get("/api/v1/companies/me", headers={"x-debug-role": "employer", "x-debug-sub": "emp-b"})
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] != second.json()["id"]


async def test_company_write_validation(api: tuple[AsyncClient, async_sessionmaker[AsyncSession]]) -> None:
    client, _factory = api
    headers = {"x-debug-role": "employer", "x-debug-sub": "emp-1"}
    blank = await client.put("/api/v1/companies/me", headers=headers, json={"name": "   "})
    assert blank.status_code == 422
    assert blank.json()["error"]["code"] == "validation_error"
    benefit = await client.put("/api/v1/companies/me", headers=headers, json={"name": "Лаба", "benefits": ["pizza"]})
    assert benefit.status_code == 422
    assert benefit.json()["error"]["code"] == "validation_error"


async def test_hook_creates_company_once_and_skips_candidates(
    api: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    _client, factory = api
    async with factory() as session:
        candidate = await provision_user(session, Principal(sub="can-x", role="candidate", email=None))
        await session.commit()
        employer = await provision_user(session, Principal(sub="emp-x", role="employer", email="e@lab.test"))
        await session.commit()
        again = await provision_user(session, Principal(sub="emp-x", role="employer", email="e@lab.test"))
        await session.commit()
        candidate_companies = list(await session.scalars(select(Company).where(Company.owner_user_id == candidate.id)))
        employer_companies = list(await session.scalars(select(Company).where(Company.owner_user_id == employer.id)))
    assert candidate_companies == []
    assert len(employer_companies) == 1
    assert again.id == employer.id
