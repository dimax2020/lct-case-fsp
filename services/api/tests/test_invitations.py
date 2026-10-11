import json
import os
import socket
import subprocess
import time
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from app.assessment import models as assessment_models  # noqa: F401
from app.chat import models as chat_models  # noqa: F401
from app.company.models import Company
from app.core.auth import Principal, get_principal
from app.core.db import Base, get_session
from app.core.errors import AppError
from app.core.models import User
from app.invitation.models import Favorite, Invitation
from app.invitation.service import build_candidate_card, expire_due, expire_invitation
from app.main import app
from app.need.models import Need
from app.need.schemas import CandidateCard
from app.profile.models import Candidate, CandidateSkill, Experience, FspAchievement, Project
from app.resume import models as resume_models  # noqa: F401
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.requests import Request

DSN = os.environ.get("FSP_TEST_DSN", "postgresql+asyncpg://fsp:fsp@127.0.0.1:54329/fsp_agent_e")
DESCRIPTION = "Команда развивает платёжный контур и сопровождает сервисы. " * 8
LOGIN_EMAIL = "login-hidden@candidate.test"
CANDIDATE_EMAIL = "hidden-card@candidate.test"
PHONE = "+79001112233"
RECRUITER_EMAIL = "hr@company.test"
RECRUITER_PHONE = "+79000000001"
CONTACT_VALUE = "tg-secret-777"
SECRETS = (CANDIDATE_EMAIL, LOGIN_EMAIL, PHONE, RECRUITER_EMAIL, RECRUITER_PHONE, CONTACT_VALUE)
EMPLOYER = {"x-debug-role": "employer", "x-debug-sub": "emp-1", "x-debug-email": "boss@lab.test"}
CANDIDATE = {"x-debug-role": "candidate", "x-debug-sub": "can-1", "x-debug-email": LOGIN_EMAIL}
STATES = ["sent", "viewed", "accepted", "declined", "expired", "revoked"]
ACTIONS = ["view", "accept", "decline", "revoke", "expire", "remind"]
LEGAL = {
    ("sent", "view"): "viewed",
    ("sent", "revoke"): "revoked",
    ("sent", "expire"): "expired",
    ("sent", "remind"): "sent",
    ("viewed", "view"): "viewed",
    ("viewed", "accept"): "accepted",
    ("viewed", "decline"): "declined",
    ("viewed", "revoke"): "revoked",
    ("viewed", "expire"): "expired",
    ("viewed", "remind"): "viewed",
}
CASES = [(state, action, LEGAL.get((state, action))) for state in STATES for action in ACTIONS]


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


def invite_body(need_id: UUID, candidate_id: UUID, **extra: object) -> dict[str, object]:
    body: dict[str, object] = {
        "need_id": str(need_id),
        "candidate_id": str(candidate_id),
        "title": "Backend-разработчик",
        "message": "Будем рады видеть в команде",
        "salary_from": 200_000,
        "salary_to": 320_000,
        "contact_channel": "telegram",
        "contact_value": CONTACT_VALUE,
        "deadline": (datetime.now(UTC) + timedelta(days=5)).isoformat(),
    }
    body.update(extra)
    return body


def make_need(company_id: UUID, title: str) -> Need:
    return Need(
        company_id=company_id,
        title=title,
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
        status="open",
    )


async def bootstrap(factory: async_sessionmaker[AsyncSession]) -> dict[str, UUID]:
    async with factory() as session:
        employer = User(kc_sub="emp-1", role="employer", email="boss@lab.test")
        candidate_user = User(kc_sub="can-1", role="candidate", email=LOGIN_EMAIL)
        session.add_all([employer, candidate_user])
        await session.flush()
        company = Company(
            owner_user_id=employer.id,
            name="ФСП Лаб",
            city="Новосибирск",
            size="51-200",
            industry="финтех",
            about="Команда платформы",
            recruiter_contact={"name": "Ирина", "email": RECRUITER_EMAIL, "phone": RECRUITER_PHONE},
            benefits=["dms"],
        )
        session.add(company)
        await session.flush()
        candidate = Candidate(
            user_id=candidate_user.id,
            full_name="Мария Соколова",
            city="Казань",
            specialization="backend",
            grade="middle",
            grade_score=81.5,
            phone=PHONE,
            contact_email=CANDIDATE_EMAIL,
            formats=["remote"],
            status="seeking",
            visible=True,
        )
        session.add(candidate)
        await session.flush()
        need = make_need(company.id, "Backend")
        session.add(need)
        session.add(CandidateSkill(candidate_id=candidate.id, skill_id="go", score=80, source="test"))
        session.add(Project(candidate_id=candidate.id, task="Платёжный шлюз", role="owner", skills=["go"]))
        session.add(
            Experience(
                candidate_id=candidate.id,
                company="Банк",
                role="Backend",
                start=date(2022, 1, 1),
                description="платежи",
            )
        )
        session.add(FspAchievement(candidate_id=candidate.id, discipline="алгоритмы", event="Финал", place=2, year=2024))
        await session.commit()
        return {
            "company_id": company.id,
            "candidate_id": candidate.id,
            "need_id": need.id,
        }


async def add_need(factory: async_sessionmaker[AsyncSession], company_id: UUID, title: str) -> UUID:
    async with factory() as session:
        need = make_need(company_id, title)
        session.add(need)
        await session.commit()
        return need.id


async def add_candidate(factory: async_sessionmaker[AsyncSession], sub: str, name: str) -> UUID:
    async with factory() as session:
        user = User(kc_sub=sub, role="candidate", email=f"{sub}@example.test")
        session.add(user)
        await session.flush()
        candidate = Candidate(user_id=user.id, full_name=name, formats=["remote"], status="seeking", visible=True)
        session.add(candidate)
        await session.commit()
        return candidate.id


async def create_invite(client: AsyncClient, need_id: UUID, candidate_id: UUID, **extra: object) -> dict[str, object]:
    response = await client.post("/api/v1/invitations", headers=EMPLOYER, json=invite_body(need_id, candidate_id, **extra))
    assert response.status_code == 201, response.text
    return response.json()


def assert_secrets_absent(payload: object, allowed: set[str] | None = None) -> None:
    raw = json.dumps(payload, ensure_ascii=False, default=str)
    for secret in SECRETS:
        if allowed and secret in allowed:
            continue
        assert secret not in raw


async def read_status(factory: async_sessionmaker[AsyncSession], invitation_id: str) -> str:
    async with factory() as session:
        inv = await session.get(Invitation, UUID(invitation_id))
        assert inv is not None
        return inv.status


async def park(client: AsyncClient, factory: async_sessionmaker[AsyncSession], seeded: dict[str, UUID], state: str) -> str:
    created = await create_invite(client, seeded["need_id"], seeded["candidate_id"])
    invitation_id = str(created["id"])
    if state == "sent":
        return invitation_id
    if state == "revoked":
        response = await client.post(f"/api/v1/invitations/{invitation_id}/revoke", headers=EMPLOYER)
        assert response.status_code == 200, response.text
        return invitation_id
    if state == "expired":
        async with factory() as session:
            await expire_invitation(session, UUID(invitation_id))
        return invitation_id
    viewed = await client.post(f"/api/v1/invitations/{invitation_id}/view", headers=CANDIDATE)
    assert viewed.status_code == 200, viewed.text
    if state == "viewed":
        return invitation_id
    if state == "accepted":
        response = await client.post(f"/api/v1/invitations/{invitation_id}/accept", headers=CANDIDATE)
        assert response.status_code == 200, response.text
        return invitation_id
    if state == "declined":
        response = await client.post(
            f"/api/v1/invitations/{invitation_id}/decline",
            headers=CANDIDATE,
            json={"reason": "salary"},
        )
        assert response.status_code == 200, response.text
        return invitation_id
    raise AssertionError(state)


class Act:
    def __init__(self, status_code: int, body: dict[str, object] | None = None) -> None:
        self.status_code = status_code
        self.body = body or {}


async def act(
    client: AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    invitation_id: str,
    action: str,
) -> Act:
    if action == "expire":
        try:
            async with factory() as session:
                await expire_invitation(session, UUID(invitation_id))
        except AppError as exc:
            return Act(exc.status_code, {"error": {"code": exc.code}})
        return Act(200)
    headers = CANDIDATE if action in {"view", "accept", "decline"} else EMPLOYER
    path = f"/api/v1/invitations/{invitation_id}/{action}"
    kwargs: dict[str, object] = {"headers": headers}
    if action == "decline":
        kwargs["json"] = {"reason": "format"}
    response = await client.post(path, **kwargs)  # type: ignore[arg-type]
    return Act(response.status_code, response.json())


@pytest.mark.parametrize(("state", "action", "result"), CASES, ids=[f"{state}-{action}" for state, action, _result in CASES])
async def test_transition_matrix(
    api: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
    state: str,
    action: str,
    result: str | None,
) -> None:
    client, factory = api
    seeded = await bootstrap(factory)
    invitation_id = await park(client, factory, seeded, state)
    outcome = await act(client, factory, invitation_id, action)
    status = await read_status(factory, invitation_id)
    if result is None:
        assert outcome.status_code == 409
        assert outcome.body["error"]["code"] == "invalid_transition"  # type: ignore[index]
        assert status == state
        return
    assert outcome.status_code == 200
    assert status == result
    if action != "expire":
        assert outcome.body["status"] == result
    if action == "decline" and result == "declined":
        assert outcome.body["decline_reason"] == "format"


async def test_contacts_hidden_until_accepted(api: tuple[AsyncClient, async_sessionmaker[AsyncSession]]) -> None:
    client, factory = api
    seeded = await bootstrap(factory)
    async with factory() as session:
        hidden_card = await build_candidate_card(session, seeded["need_id"], seeded["candidate_id"])
    assert hidden_card["contacts_revealed"] is False
    assert "email" not in hidden_card
    assert "phone" not in hidden_card
    assert hidden_card["display_name"] == "Мария С."
    assert hidden_card["full_name_initials"] == "М. С."
    assert hidden_card["category"] == "backend · middle"
    assert hidden_card["skills"] == ["go"]
    assert hidden_card["projects"] == ["Платёжный шлюз"]
    assert hidden_card["fsp_badge"]["discipline"] == "алгоритмы"
    assert hidden_card["experience_years"] >= 4
    assert hidden_card["test_score"] == 81.5
    assert hidden_card["match"] == 0
    parsed = CandidateCard.model_validate(hidden_card)
    dumped = parsed.model_dump(exclude_none=True)
    assert dumped["contacts_revealed"] is False
    assert "email" not in dumped
    assert "phone" not in dumped
    assert_secrets_absent(hidden_card)

    created = await create_invite(client, seeded["need_id"], seeded["candidate_id"])
    assert created["status"] == "sent"
    assert "candidate_email" not in created
    assert "candidate_phone" not in created
    assert "recruiter_contact" not in created
    assert_secrets_absent(created)

    employer_list = await client.get("/api/v1/invitations", headers=EMPLOYER)
    candidate_list = await client.get("/api/v1/invitations", headers=CANDIDATE)
    viewed = await client.post(f"/api/v1/invitations/{created['id']}/view", headers=CANDIDATE)
    assert employer_list.status_code == 200
    assert candidate_list.status_code == 200
    assert viewed.status_code == 200
    for payload in (employer_list.json(), candidate_list.json(), viewed.json()):
        assert_secrets_absent(payload)
    assert "candidate_email" not in viewed.json()
    assert "recruiter_contact" not in viewed.json()

    async with factory() as session:
        still_hidden = await build_candidate_card(session, seeded["need_id"], seeded["candidate_id"])
    assert still_hidden["invitation_status"] == "viewed"
    assert still_hidden["contacts_revealed"] is False
    assert "email" not in still_hidden
    assert_secrets_absent(still_hidden)

    accepted = await client.post(f"/api/v1/invitations/{created['id']}/accept", headers=CANDIDATE)
    assert accepted.status_code == 200, accepted.text
    accepted_body = accepted.json()
    assert accepted_body["status"] == "accepted"
    assert RECRUITER_EMAIL in accepted_body["recruiter_contact"]
    assert RECRUITER_PHONE in accepted_body["recruiter_contact"]
    assert CONTACT_VALUE in accepted_body["recruiter_contact"]
    assert "candidate_email" not in accepted_body
    assert "candidate_phone" not in accepted_body
    assert LOGIN_EMAIL not in json.dumps(accepted_body)
    assert CANDIDATE_EMAIL not in json.dumps(accepted_body)
    assert PHONE not in json.dumps(accepted_body)

    employer_after = await client.get("/api/v1/invitations", headers=EMPLOYER)
    candidate_after = await client.get("/api/v1/invitations", headers=CANDIDATE)
    employer_item = employer_after.json()["items"][0]
    candidate_item = candidate_after.json()["items"][0]
    assert employer_item["candidate_email"] == CANDIDATE_EMAIL
    assert employer_item["candidate_phone"] == PHONE
    assert "recruiter_contact" not in employer_item
    assert RECRUITER_EMAIL not in json.dumps(employer_item)
    assert CONTACT_VALUE not in json.dumps(employer_item)
    assert LOGIN_EMAIL not in json.dumps(employer_item)
    assert candidate_item["recruiter_contact"]
    assert "candidate_email" not in candidate_item
    assert CANDIDATE_EMAIL not in json.dumps(candidate_item)
    assert PHONE not in json.dumps(candidate_item)

    async with factory() as session:
        revealed = await build_candidate_card(session, seeded["need_id"], seeded["candidate_id"])
    assert revealed["contacts_revealed"] is True
    assert revealed["email"] == CANDIDATE_EMAIL
    assert revealed["phone"] == PHONE
    assert revealed["invitation_status"] == "accepted"
    revealed_dump = json.dumps(revealed, ensure_ascii=False, default=str)
    assert LOGIN_EMAIL not in revealed_dump
    assert RECRUITER_EMAIL not in revealed_dump
    assert CONTACT_VALUE not in revealed_dump
    assert CandidateCard.model_validate(revealed).email == CANDIDATE_EMAIL


async def test_lists_filters_and_counters(api: tuple[AsyncClient, async_sessionmaker[AsyncSession]]) -> None:
    client, factory = api
    seeded = await bootstrap(factory)
    other_id = await add_candidate(factory, "can-2", "Иван Петров")
    titles = ["Ждёт", "Открыто", "Принято", "Отказ"]
    need_ids = [seeded["need_id"]]
    for title in titles[1:]:
        need_ids.append(await add_need(factory, seeded["company_id"], title))
    await create_invite(client, need_ids[0], seeded["candidate_id"])
    viewed = await create_invite(client, need_ids[1], seeded["candidate_id"])
    accepted = await create_invite(client, need_ids[2], seeded["candidate_id"])
    declined = await create_invite(client, need_ids[3], seeded["candidate_id"])
    other_need = await add_need(factory, seeded["company_id"], "Чужой")
    await create_invite(client, other_need, other_id)
    assert (await client.post(f"/api/v1/invitations/{viewed['id']}/view", headers=CANDIDATE)).status_code == 200
    assert (await client.post(f"/api/v1/invitations/{accepted['id']}/view", headers=CANDIDATE)).status_code == 200
    assert (await client.post(f"/api/v1/invitations/{accepted['id']}/accept", headers=CANDIDATE)).status_code == 200
    assert (await client.post(f"/api/v1/invitations/{declined['id']}/view", headers=CANDIDATE)).status_code == 200
    assert (
        await client.post(
            f"/api/v1/invitations/{declined['id']}/decline",
            headers=CANDIDATE,
            json={"reason": "stack"},
        )
    ).status_code == 200

    employer = await client.get("/api/v1/invitations", headers=EMPLOYER)
    assert employer.status_code == 200
    body = employer.json()
    assert body["counts"]["sent"] == 2
    assert body["counts"]["viewed"] == 1
    assert body["counts"]["accepted"] == 1
    assert body["counts"]["declined"] == 1
    assert body["counts"]["expired"] == 0
    assert body["counts"]["waiting"] == 3
    assert body["counts"]["all"] == 5
    assert len(body["items"]) == 5

    waiting = await client.get("/api/v1/invitations", headers=EMPLOYER, params={"status": "waiting"})
    assert {item["status"] for item in waiting.json()["items"]} == {"sent", "viewed"}
    assert len(waiting.json()["items"]) == 3
    assert waiting.json()["counts"]["all"] == 5

    only_accepted = await client.get("/api/v1/invitations", headers=EMPLOYER, params={"status": "accepted"})
    assert [item["status"] for item in only_accepted.json()["items"]] == ["accepted"]

    candidate = await client.get("/api/v1/invitations", headers=CANDIDATE, params={"status": "incoming"})
    assert candidate.status_code == 200
    assert {item["status"] for item in candidate.json()["items"]} == {"sent", "viewed"}
    assert candidate.json()["counts"]["all"] == 4
    assert candidate.json()["counts"]["incoming"] == 2
    declined_tab = await client.get("/api/v1/invitations", headers=CANDIDATE, params={"status": "declined"})
    assert [item["decline_reason"] for item in declined_tab.json()["items"]] == ["stack"]
    accepted_tab = await client.get("/api/v1/invitations", headers=CANDIDATE, params={"status": "accepted"})
    assert len(accepted_tab.json()["items"]) == 1

    mismatch = await client.get("/api/v1/invitations", headers=EMPLOYER, params={"role": "candidate"})
    assert mismatch.status_code == 403
    unknown = await client.get("/api/v1/invitations", headers=EMPLOYER, params={"status": "nope"})
    assert unknown.status_code == 422
    assert unknown.json()["error"]["code"] == "validation_error"


async def test_salary_fork_uniqueness_and_ownership(
    api: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, factory = api
    seeded = await bootstrap(factory)
    missing = invite_body(seeded["need_id"], seeded["candidate_id"])
    del missing["salary_to"]
    response = await client.post("/api/v1/invitations", headers=EMPLOYER, json=missing)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    inverted = invite_body(seeded["need_id"], seeded["candidate_id"], salary_from=300_000, salary_to=100_000)
    response = await client.post("/api/v1/invitations", headers=EMPLOYER, json=inverted)
    assert response.status_code == 422
    assert "вилк" in response.json()["error"]["message"]

    created = await create_invite(client, seeded["need_id"], seeded["candidate_id"])
    duplicate = await client.post(
        "/api/v1/invitations",
        headers=EMPLOYER,
        json=invite_body(seeded["need_id"], seeded["candidate_id"]),
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "invitation_exists"

    async with factory() as session:
        other = User(kc_sub="emp-2", role="employer", email="other@lab.test")
        session.add(other)
        await session.flush()
        company = Company(owner_user_id=other.id, name="Другая", recruiter_contact={}, benefits=[])
        session.add(company)
        await session.flush()
        foreign = make_need(company.id, "Чужая")
        session.add(foreign)
        await session.commit()
        foreign_id = foreign.id
    foreign_response = await client.post(
        "/api/v1/invitations",
        headers=EMPLOYER,
        json=invite_body(foreign_id, seeded["candidate_id"]),
    )
    assert foreign_response.status_code == 404
    assert foreign_response.json()["error"]["code"] == "not_found"
    missing_candidate = await client.post(
        "/api/v1/invitations",
        headers=EMPLOYER,
        json=invite_body(seeded["need_id"], uuid4()),
    )
    assert missing_candidate.status_code == 404

    accept = await client.post(f"/api/v1/invitations/{created['id']}/accept", headers=EMPLOYER)
    assert accept.status_code == 403
    revoke = await client.post(f"/api/v1/invitations/{created['id']}/revoke", headers=CANDIDATE)
    assert revoke.status_code == 403


async def test_decline_reasons_and_second_view(api: tuple[AsyncClient, async_sessionmaker[AsyncSession]]) -> None:
    client, factory = api
    seeded = await bootstrap(factory)
    for reason in ("salary", "stack", "format", "found_job", "other"):
        need_id = seeded["need_id"] if reason == "salary" else await add_need(factory, seeded["company_id"], reason)
        created = await create_invite(client, need_id, seeded["candidate_id"])
        assert (await client.post(f"/api/v1/invitations/{created['id']}/view", headers=CANDIDATE)).status_code == 200
        async with factory() as session:
            first = await session.get(Invitation, UUID(str(created["id"])))
            assert first is not None
            stamp = first.viewed_at
        again = await client.post(f"/api/v1/invitations/{created['id']}/view", headers=CANDIDATE)
        assert again.status_code == 200
        assert again.json()["status"] == "viewed"
        async with factory() as session:
            saved = await session.get(Invitation, UUID(str(created["id"])))
            assert saved is not None
            assert saved.viewed_at == stamp
        declined = await client.post(
            f"/api/v1/invitations/{created['id']}/decline",
            headers=CANDIDATE,
            json={"reason": reason},
        )
        assert declined.status_code == 200, declined.text
        assert declined.json()["decline_reason"] == reason
    bad = await client.post(
        "/api/v1/invitations/00000000-0000-0000-0000-000000000000/decline",
        headers=CANDIDATE,
        json={"reason": "work_format"},
    )
    assert bad.status_code == 422


async def test_favorites(api: tuple[AsyncClient, async_sessionmaker[AsyncSession]]) -> None:
    client, factory = api
    seeded = await bootstrap(factory)
    added = await client.post(f"/api/v1/favorites/{seeded['candidate_id']}", headers=EMPLOYER)
    assert added.status_code == 200
    assert added.json() == {"candidate_id": str(seeded["candidate_id"]), "favorite": True}
    again = await client.post(f"/api/v1/favorites/{seeded['candidate_id']}", headers=EMPLOYER)
    assert again.status_code == 200
    assert again.json()["favorite"] is True
    forbidden = await client.post(f"/api/v1/favorites/{seeded['candidate_id']}", headers=CANDIDATE)
    assert forbidden.status_code == 403
    missing = await client.post(f"/api/v1/favorites/{uuid4()}", headers=EMPLOYER)
    assert missing.status_code == 404
    async with factory() as session:
        stored = await session.scalar(
            select(Favorite).where(
                Favorite.company_id == seeded["company_id"],
                Favorite.candidate_id == seeded["candidate_id"],
            )
        )
    assert stored is not None
    removed = await client.delete(f"/api/v1/favorites/{seeded['candidate_id']}", headers=EMPLOYER)
    assert removed.json() == {"candidate_id": str(seeded["candidate_id"]), "favorite": False}
    removed_again = await client.delete(f"/api/v1/favorites/{seeded['candidate_id']}", headers=EMPLOYER)
    assert removed_again.json()["favorite"] is False
    async with factory() as session:
        row = await session.scalar(
            select(Favorite).where(
                Favorite.company_id == seeded["company_id"],
                Favorite.candidate_id == seeded["candidate_id"],
            )
        )
    assert row is None


async def test_status_changes_invalidate_shortlist(api: tuple[AsyncClient, async_sessionmaker[AsyncSession]]) -> None:
    client, factory = api
    seeded = await bootstrap(factory)
    need_id = seeded["need_id"]
    with patch("app.invitation.service.invalidate", new_callable=AsyncMock) as mocked:
        created = await create_invite(client, need_id, seeded["candidate_id"])
        mocked.assert_awaited_with(need_id)
        mocked.reset_mock()
        denied = await client.post(f"/api/v1/invitations/{created['id']}/accept", headers=CANDIDATE)
        assert denied.status_code == 409
        mocked.assert_not_awaited()
        assert (await client.post(f"/api/v1/invitations/{created['id']}/view", headers=CANDIDATE)).status_code == 200
        mocked.assert_awaited_with(need_id)
        mocked.reset_mock()
        assert (await client.post(f"/api/v1/invitations/{created['id']}/view", headers=CANDIDATE)).status_code == 200
        assert (await client.post(f"/api/v1/invitations/{created['id']}/remind", headers=EMPLOYER)).status_code == 200
        mocked.assert_not_awaited()
        assert (await client.post(f"/api/v1/invitations/{created['id']}/accept", headers=CANDIDATE)).status_code == 200
        mocked.assert_awaited_with(need_id)

        mocked.reset_mock()
        other = await add_candidate(factory, "can-3", "Ольга Ильина")
        decline_need = await add_need(factory, seeded["company_id"], "Отказ")
        decline_inv = await create_invite(client, decline_need, other)
        mocked.reset_mock()
        assert (
            await client.post(
                f"/api/v1/invitations/{decline_inv['id']}/view",
                headers={
                    "x-debug-role": "candidate",
                    "x-debug-sub": "can-3",
                },
            )
        ).status_code == 200
        mocked.assert_awaited()
        mocked.reset_mock()
        assert (
            await client.post(
                f"/api/v1/invitations/{decline_inv['id']}/decline",
                headers={"x-debug-role": "candidate", "x-debug-sub": "can-3"},
                json={"reason": "other"},
            )
        ).status_code == 200
        mocked.assert_awaited_with(decline_need)

        revoke_need = await add_need(factory, seeded["company_id"], "Отзыв")
        revoke_inv = await create_invite(client, revoke_need, other)
        mocked.reset_mock()
        assert (await client.post(f"/api/v1/invitations/{revoke_inv['id']}/revoke", headers=EMPLOYER)).status_code == 200
        mocked.assert_awaited_with(revoke_need)


async def test_expire_due_only_open_deadlines(api: tuple[AsyncClient, async_sessionmaker[AsyncSession]]) -> None:
    client, factory = api
    seeded = await bootstrap(factory)
    past = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    future = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    due = await create_invite(client, seeded["need_id"], seeded["candidate_id"], deadline=past)
    future_need = await add_need(factory, seeded["company_id"], "Будущее")
    future_candidate = await add_candidate(factory, "can-future", "Пётр Сидоров")
    waiting = await create_invite(client, future_need, future_candidate, deadline=future)
    open_need = await add_need(factory, seeded["company_id"], "Без срока")
    open_candidate = await add_candidate(factory, "can-open", "Анна Орлова")
    no_deadline = await create_invite(client, open_need, open_candidate, deadline=None)
    viewed_need = await add_need(factory, seeded["company_id"], "Просмотрено")
    viewed_candidate = await add_candidate(factory, "can-viewed", "Кирилл Носов")
    viewed = await create_invite(client, viewed_need, viewed_candidate, deadline=past)
    assert (
        await client.post(
            f"/api/v1/invitations/{viewed['id']}/view",
            headers={
                "x-debug-role": "candidate",
                "x-debug-sub": "can-viewed",
            },
        )
    ).status_code == 200
    accepted_need = await add_need(factory, seeded["company_id"], "Принято")
    accepted_candidate = await add_candidate(factory, "can-accepted", "Ева Морозова")
    accepted = await create_invite(client, accepted_need, accepted_candidate, deadline=past)
    accepted_headers = {"x-debug-role": "candidate", "x-debug-sub": "can-accepted"}
    assert (await client.post(f"/api/v1/invitations/{accepted['id']}/view", headers=accepted_headers)).status_code == 200
    assert (await client.post(f"/api/v1/invitations/{accepted['id']}/accept", headers=accepted_headers)).status_code == 200
    async with factory() as session:
        saved = await session.get(Invitation, UUID(str(accepted["id"])))
        assert saved is not None
        saved.deadline = datetime.now(UTC) - timedelta(hours=3)
        await session.commit()

    with patch("app.invitation.service.invalidate", new_callable=AsyncMock) as mocked:
        async with factory() as session:
            expired = await expire_due(session)
        assert expired == 2
        assert mocked.await_count == 2
        mocked.assert_any_await(seeded["need_id"])
        mocked.assert_any_await(viewed_need)

    assert await read_status(factory, str(due["id"])) == "expired"
    assert await read_status(factory, str(viewed["id"])) == "expired"
    assert await read_status(factory, str(waiting["id"])) == "sent"
    assert await read_status(factory, str(no_deadline["id"])) == "sent"
    assert await read_status(factory, str(accepted["id"])) == "accepted"


def test_expire_task_is_scheduled() -> None:
    from app.tasks import broker

    tasks = broker.get_all_tasks()
    found = [task for name, task in tasks.items() if "expire_overdue_invitations" in name]
    assert found, list(tasks)
    schedule = found[0].labels.get("schedule")
    assert schedule
    assert schedule[0]["cron"] == "*/5 * * * *"
