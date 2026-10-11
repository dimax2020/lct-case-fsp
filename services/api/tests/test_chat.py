import asyncio
import os
import socket
import subprocess
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from app.assessment import models as assessment_models  # noqa: F401
from app.chat import models as chat_models  # noqa: F401
from app.company.models import Company
from app.core.auth import Principal, get_principal
from app.core.db import Base, get_session
from app.core.models import User
from app.invitation.models import Invitation
from app.main import app
from app.need.models import Need
from app.profile.models import Candidate
from app.resume import models as resume_models  # noqa: F401
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.requests import Request

DSN = os.environ.get("FSP_TEST_DSN", "postgresql+asyncpg://fsp:fsp@127.0.0.1:54329/fsp_agent_e")
DESCRIPTION = "Команда развивает платёжный контур и сопровождает сервисы. " * 8
EMPLOYER = {"x-debug-role": "employer", "x-debug-sub": "emp-1", "x-debug-email": "boss@lab.test"}
CANDIDATE = {"x-debug-role": "candidate", "x-debug-sub": "can-1", "x-debug-email": "can@lab.test"}


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


async def seed(factory: async_sessionmaker[AsyncSession]) -> dict[str, UUID]:
    async with factory() as session:
        employer = User(kc_sub="emp-1", role="employer", email="boss@lab.test")
        candidate_user = User(kc_sub="can-1", role="candidate", email="can@lab.test")
        session.add_all([employer, candidate_user])
        await session.flush()
        company = Company(
            owner_user_id=employer.id,
            name="ФСП Лаб",
            recruiter_contact={"email": "hr@company.test"},
            benefits=["dms"],
        )
        session.add(company)
        await session.flush()
        candidate = Candidate(
            user_id=candidate_user.id,
            full_name="Мария Соколова",
            phone="+79001112233",
            contact_email="hidden-card@candidate.test",
            formats=["remote"],
            status="seeking",
            visible=True,
        )
        session.add(candidate)
        await session.flush()
        need = Need(
            company_id=company.id,
            title="Backend",
            specialization="backend",
            grades=["middle"],
            salary_from=200_000,
            salary_to=320_000,
            formats=["remote"],
            must_skills=["go"],
            nice_skills=[],
            description=DESCRIPTION,
            domain="fintech",
            stages=2,
        )
        session.add(need)
        await session.commit()
        return {"need_id": need.id, "candidate_id": candidate.id}


async def test_messages_require_accepted_invitation(api: tuple[AsyncClient, async_sessionmaker[AsyncSession]]) -> None:
    client, factory = api
    seeded = await seed(factory)
    created = await client.post(
        "/api/v1/invitations",
        headers=EMPLOYER,
        json={
            "need_id": str(seeded["need_id"]),
            "candidate_id": str(seeded["candidate_id"]),
            "title": "Backend-разработчик",
            "message": "Ждём вас",
            "salary_from": 200_000,
            "salary_to": 320_000,
            "contact_channel": "email",
            "contact_value": "hr@company.test",
        },
    )
    assert created.status_code == 201, created.text
    invitation_id = created.json()["id"]
    early = await client.post(
        f"/api/v1/invitations/{invitation_id}/messages",
        headers=EMPLOYER,
        json={"kind": "text", "body": "Рано"},
    )
    assert early.status_code == 409
    assert early.json()["error"]["code"] == "invitation_not_accepted"
    assert (await client.post(f"/api/v1/invitations/{invitation_id}/view", headers=CANDIDATE)).status_code == 200
    still = await client.get(f"/api/v1/invitations/{invitation_id}/messages", headers=CANDIDATE)
    assert still.status_code == 409

    assert (await client.post(f"/api/v1/invitations/{invitation_id}/accept", headers=CANDIDATE)).status_code == 200
    empty = await client.get(f"/api/v1/invitations/{invitation_id}/messages", headers=EMPLOYER)
    assert empty.status_code == 200
    assert empty.json()["items"] == []

    first = await client.post(
        f"/api/v1/invitations/{invitation_id}/messages",
        headers=EMPLOYER,
        json={"kind": "text", "body": "Когда удобно созвониться?"},
    )
    assert first.status_code == 201, first.text
    await asyncio.sleep(0.02)
    second = await client.post(
        f"/api/v1/invitations/{invitation_id}/messages",
        headers=CANDIDATE,
        json={"kind": "text", "body": "Завтра после обеда"},
    )
    assert second.status_code == 201, second.text
    listed = await client.get(f"/api/v1/invitations/{invitation_id}/messages", headers=CANDIDATE)
    bodies = [item["body"] for item in listed.json()["items"]]
    assert bodies == ["Когда удобно созвониться?", "Завтра после обеда"]
    newer = await client.get(
        f"/api/v1/invitations/{invitation_id}/messages",
        headers=EMPLOYER,
        params={"after": first.json()["created_at"]},
    )
    assert [item["body"] for item in newer.json()["items"]] == ["Завтра после обеда"]

    start = datetime.now(UTC) + timedelta(days=1)
    end = start + timedelta(hours=1)
    slots = await client.post(
        f"/api/v1/invitations/{invitation_id}/messages",
        headers=EMPLOYER,
        json={
            "kind": "slots",
            "body": "Могу в это окно",
            "slots": [{"start": start.isoformat(), "end": end.isoformat()}],
        },
    )
    assert slots.status_code == 201, slots.text
    assert slots.json()["kind"] == "slots"
    assert len(slots.json()["slots"]) == 1

    system = await client.post(
        f"/api/v1/invitations/{invitation_id}/messages",
        headers=EMPLOYER,
        json={"kind": "system", "body": "Переходим к команде"},
    )
    assert system.status_code == 201
    assert system.json()["kind"] == "system"

    for stage in ("interview", "team", "offer", "closed"):
        marked = await client.post(
            f"/api/v1/invitations/{invitation_id}/messages",
            headers=EMPLOYER,
            json={"kind": "text", "body": f"Этап {stage}", "hiring_stage": stage},
        )
        assert marked.status_code == 201, marked.text
        assert marked.json()["hiring_stage"] == stage
    async with factory() as session:
        inv = await session.get(Invitation, UUID(invitation_id))
        assert inv is not None
        assert inv.hiring_stage == "closed"

    denied = await client.post(
        f"/api/v1/invitations/{invitation_id}/messages",
        headers=CANDIDATE,
        json={"kind": "text", "body": "сам поставлю", "hiring_stage": "offer"},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "forbidden"
    after_denied = await client.get(f"/api/v1/invitations/{invitation_id}/messages", headers=EMPLOYER)
    assert all(item["body"] != "сам поставлю" for item in after_denied.json()["items"])

    empty_text = await client.post(
        f"/api/v1/invitations/{invitation_id}/messages",
        headers=CANDIDATE,
        json={"kind": "text", "body": "   "},
    )
    assert empty_text.status_code == 422
    bad_slot = await client.post(
        f"/api/v1/invitations/{invitation_id}/messages",
        headers=EMPLOYER,
        json={"kind": "slots", "slots": [{"start": start.isoformat(), "end": start.isoformat()}]},
    )
    assert bad_slot.status_code == 422

    stranger = await client.get(
        f"/api/v1/invitations/{invitation_id}/messages",
        headers={"x-debug-role": "employer", "x-debug-sub": "emp-stranger"},
    )
    assert stranger.status_code == 403


async def test_revoked_invitation_has_no_chat(api: tuple[AsyncClient, async_sessionmaker[AsyncSession]]) -> None:
    client, factory = api
    seeded = await seed(factory)
    created = await client.post(
        "/api/v1/invitations",
        headers=EMPLOYER,
        json={
            "need_id": str(seeded["need_id"]),
            "candidate_id": str(seeded["candidate_id"]),
            "title": "Backend",
            "message": "Отозвали",
            "salary_from": 10,
            "salary_to": 20,
            "contact_channel": "phone",
            "contact_value": "+70000000000",
        },
    )
    invitation_id = created.json()["id"]
    assert (await client.post(f"/api/v1/invitations/{invitation_id}/revoke", headers=EMPLOYER)).status_code == 200
    response = await client.post(
        f"/api/v1/invitations/{invitation_id}/messages",
        headers=EMPLOYER,
        json={"kind": "text", "body": "ещё тут?"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invitation_not_accepted"
