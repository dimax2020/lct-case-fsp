"""Сквозной сценарий теста рабочего стиля и настроек приватности через HTTP API.

Нужен Postgres с pgvector — как и остальным интеграционным тестам (см. test_company.py).
"""

import os
import socket
import subprocess
import time
from collections.abc import AsyncIterator

import app.profile.router as profile_router
import app.psych.router as psych_router
import pytest
from app.core.auth import Principal, get_principal
from app.core.db import Base, get_session
from app.main import app
from app.psych import models as psych_models  # noqa: F401
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
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
    """Тот же контейнер, что и в test_company.py."""
    if os.environ.get("FSP_TEST_DSN") or _port_open("127.0.0.1", 54329):
        return DSN
    subprocess.run(
        ["docker", "run", "-d", "--name", "fsp-agent-e-pg", "-e", "POSTGRES_USER=fsp", "-e", "POSTGRES_PASSWORD=fsp",
         "-e", "POSTGRES_DB=fsp_agent_e", "-p", "127.0.0.1:54329:5432", "pgvector/pgvector:pg16"],
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
    return Principal(sub=sub, role=role if role in {"candidate", "employer", "admin"} else "candidate", email=email)

CANDIDATE = {"x-debug-role": "candidate", "x-debug-sub": "psy-candidate", "x-debug-email": "psy@example.com"}
EMPLOYER = {"x-debug-role": "employer", "x-debug-sub": "psy-employer", "x-debug-email": "hr@example.com"}


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    engine = create_async_engine(ensure_test_postgres(), pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    async with factory() as session:
        names = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
        await session.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
        await session.commit()

    async def plain_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    async def committing_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session
            await session.commit()

    app.dependency_overrides[get_principal] = debug_principal
    app.dependency_overrides[get_session] = plain_session
    app.dependency_overrides[psych_router._db] = committing_session
    app.dependency_overrides[profile_router._db] = committing_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        try:
            yield http
        finally:
            app.dependency_overrides.clear()
    await engine.dispose()


def _answers() -> dict:
    return {
        "disc": {str(i): {"most": "а", "least": "в"} for i in range(1, 13)},
        "statements": {str(i): (4 if i % 3 else 2) for i in range(1, 31)},
        "cases": {str(i): "б" for i in range(1, 6)},
    }


async def test_psych_flow_and_employer_visibility(client: AsyncClient) -> None:
    test = await client.get("/api/v1/psych/test", headers=CANDIDATE)
    assert test.status_code == 200
    assert "points" not in test.text and "weights" not in test.text

    started = await client.post("/api/v1/psych/attempts", headers=CANDIDATE)
    assert started.status_code == 201
    attempt_id = started.json()["id"]
    again = await client.post("/api/v1/psych/attempts", headers=CANDIDATE)
    assert again.json()["id"] == attempt_id

    saved = await client.put(f"/api/v1/psych/attempts/{attempt_id}", json={"statements": {"1": 5}}, headers=CANDIDATE)
    assert saved.status_code == 200
    assert saved.json()["progress"]["statements_done"] == 1

    finished = await client.post(
        f"/api/v1/psych/attempts/{attempt_id}/finish",
        json={"answers": _answers(), "share_with_employers": True},
        headers=CANDIDATE,
    )
    assert finished.status_code == 200
    state = finished.json()
    assert state["result"]["disc_profile"]["label"]
    assert "flags" not in state["result"]
    assert state["share_with_employers"] is True
    assert state["can_start"] is False

    retake = await client.post("/api/v1/psych/attempts", headers=CANDIDATE)
    assert retake.status_code == 409

    me = await client.get("/api/v1/me", headers=CANDIDATE)
    candidate_id = me.json()["candidate_id"]
    await client.get("/api/v1/companies/me", headers=EMPLOYER)
    view = await client.get(f"/api/v1/psych/candidates/{candidate_id}", headers=EMPLOYER)
    assert view.status_code == 200
    body = view.json()
    assert body["available"] is True
    assert "flags" in body["result"] and len(body["result"]["fits"]) == 5

    closed = await client.put("/api/v1/psych/me/share", json={"share_with_employers": False}, headers=CANDIDATE)
    assert closed.json()["share_with_employers"] is False
    hidden = await client.get(f"/api/v1/psych/candidates/{candidate_id}", headers=EMPLOYER)
    assert hidden.json()["available"] is False


async def test_privacy_settings_and_company_search(client: AsyncClient) -> None:
    company = await client.put(
        "/api/v1/companies/me",
        json={"name": "Скрытая Лаб", "website": "lab.example.ru", "logo": None},
        headers=EMPLOYER,
    )
    assert company.status_code == 200
    assert company.json()["website"] == "https://lab.example.ru"
    company_id = company.json()["id"]

    found = await client.get("/api/v1/companies", params={"q": "скрыт"}, headers=CANDIDATE)
    assert [item["id"] for item in found.json()] == [company_id]

    settings = await client.get("/api/v1/candidates/me/settings", headers=CANDIDATE)
    payload = settings.json()
    payload.update(
        {
            "hidden_company_ids": [company_id],
            "show_full_name": True,
            "show_fsp": False,
            "consent_processing": True,
        }
    )
    updated = await client.put("/api/v1/candidates/me/settings", json=payload, headers=CANDIDATE)
    data = updated.json()
    assert data["hidden_companies"] == [{"id": company_id, "name": "Скрытая Лаб"}]
    assert data["show_full_name"] is True and data["show_fsp"] is False
    assert data["consent_processing_at"] is not None

    me = await client.get("/api/v1/me", headers=CANDIDATE)
    candidate_id = me.json()["candidate_id"]
    bank = await client.get("/api/v1/candidates", headers=EMPLOYER)
    assert candidate_id not in [item["id"] for item in bank.json()]
    psych = await client.get(f"/api/v1/psych/candidates/{candidate_id}", headers=EMPLOYER)
    assert psych.status_code == 404

    unlinked = await client.delete("/api/v1/candidates/me/fsp-link", headers=CANDIDATE)
    assert unlinked.status_code == 200
    assert unlinked.json()["fsp_achievements"] == []
