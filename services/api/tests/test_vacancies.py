"""Vacancy catalog, applications, and contact visibility."""

import json
import os
import socket
import subprocess
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from app.assessment import models as assessment_models  # noqa: F401
from app.chat import models as chat_models  # noqa: F401
from app.company.models import Company
from app.core.auth import Principal, get_principal
from app.core.db import Base, get_session
from app.core.errors import AppError
from app.core.models import User
from app.invitation.models import Invitation
from app.main import app
from app.need.models import Need
from app.profile.models import Candidate
from app.resume import models as resume_models  # noqa: F401
from app.vacancy.models import Application, Vacancy
from app.vacancy.schemas import (
    VacancyWrite,
    applicant_email,
    check_grades,
    ensure_vacancy_bounds,
    public_application,
    status_counts,
)
from app.vacancy.seed_extra import DEMO_VACANCIES
from app.vacancy.service import _apply_transition, next_application_status, resolve_list_role, vacancy_visible
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.requests import Request

DESCRIPTION = "Команда развивает платёжный контур и сопровождает сервисы каждый день."
LOGIN_A = "login-a@secret.test"
CONTACT_A = "applicant-self@secret.test"
PHONE_A = "+70000000097"
CONTACT_B = "other-applicant@secret.test"
PHONE_B = "+70000000098"
CONTACT_C = "leak-not-applied@secret.test"
PHONE_C = "+70000000099"
NOW = datetime(2026, 10, 11, tzinfo=UTC)
EMPLOYER = {"x-debug-role": "employer", "x-debug-sub": "emp-1", "x-debug-email": "boss@lab.test"}
OTHER_EMPLOYER = {"x-debug-role": "employer", "x-debug-sub": "emp-2", "x-debug-email": "other@lab.test"}
CANDIDATE = {"x-debug-role": "candidate", "x-debug-sub": "can-1", "x-debug-email": LOGIN_A}
CANDIDATE_B = {"x-debug-role": "candidate", "x-debug-sub": "can-2", "x-debug-email": "login-b@secret.test"}
STATES = ["sent", "viewed", "accepted", "declined"]
ACTIONS = ["view", "accept", "decline"]
LEGAL = {
    ("sent", "view"): "viewed",
    ("sent", "accept"): "accepted",
    ("sent", "decline"): "declined",
    ("viewed", "view"): "viewed",
    ("viewed", "accept"): "accepted",
    ("viewed", "decline"): "declined",
}


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.3):
            return True
    except OSError:
        return False


def _start_docker() -> bool:
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            "fsp-agent-v-pg",
            "-e",
            "POSTGRES_USER=fsp",
            "-e",
            "POSTGRES_PASSWORD=fsp",
            "-e",
            "POSTGRES_DB=fsp_agent_v",
            "-p",
            "127.0.0.1:54330:5432",
            "pgvector/pgvector:pg16",
        ],
        check=False,
        capture_output=True,
        timeout=90,
    )
    subprocess.run(["docker", "start", "fsp-agent-v-pg"], check=False, capture_output=True, timeout=30)
    for _ in range(40):
        if _port_open("127.0.0.1", 54330):
            return True
        time.sleep(0.25)
    return False


async def _dedicated(admin_dsn: str, name: str) -> str:
    engine = create_async_engine(admin_dsn, isolation_level="AUTOCOMMIT", pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            exists = await conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": name})
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        await engine.dispose()
    base, _db = admin_dsn.rsplit("/", 1)
    return f"{base}/{name}"


async def postgres_dsn() -> str | None:
    env = os.environ.get("FSP_TEST_DSN", "").strip()
    if env:
        return env
    if _port_open("127.0.0.1", 54330):
        return "postgresql+asyncpg://fsp:fsp@127.0.0.1:54330/fsp_agent_v"
    if _port_open("127.0.0.1", 54329):
        try:
            return await _dedicated("postgresql+asyncpg://fsp:fsp@127.0.0.1:54329/fsp_agent_e", "fsp_vacancies")
        except Exception:
            return None
    if _port_open("127.0.0.1", 5432):
        for admin in (
            "postgresql+asyncpg://fsp:fsp@127.0.0.1:5432/postgres",
            "postgresql+asyncpg://fsp:fsp@127.0.0.1:5432/fsp",
        ):
            try:
                return await _dedicated(admin, "fsp_vacancies")
            except Exception:
                continue
    try:
        if _start_docker():
            return "postgresql+asyncpg://fsp:fsp@127.0.0.1:54330/fsp_agent_v"
    except (OSError, subprocess.TimeoutExpired):
        return None
    return None


async def debug_principal(request: Request) -> Principal:
    role = request.headers.get("x-debug-role", "candidate")
    sub = request.headers.get("x-debug-sub", "stub-candidate")
    email = request.headers.get("x-debug-email")
    if role not in {"candidate", "employer", "admin"}:
        role = "candidate"
    return Principal(sub=sub, role=role, email=email)


@pytest.fixture
async def api() -> AsyncIterator[tuple[AsyncClient, async_sessionmaker[AsyncSession]]]:
    dsn = await postgres_dsn()
    if dsn is None:
        pytest.skip("postgres is not available")
    engine = create_async_engine(dsn, pool_pre_ping=True)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:
        await engine.dispose()
        pytest.skip(f"postgres is not available: {exc}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
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


def body(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "title": "Backend-разработчик",
        "specialization": "backend",
        "grades": ["middle", "senior"],
        "salary_from": 200_000,
        "salary_to": 320_000,
        "formats": ["remote"],
        "city": "Новосибирск",
        "must_skills": ["go"],
        "description": DESCRIPTION,
        "domain": "fintech",
    }
    payload.update(overrides)
    return payload


def _application_view(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "application_id": UUID("11111111-1111-1111-1111-111111111111"),
        "vacancy_id": UUID("22222222-2222-2222-2222-222222222222"),
        "status": "sent",
        "message": "Готов обсудить",
        "created_at": NOW,
        "title": "Backend-разработчик",
        "viewer": "candidate",
        "company_name": "ФСП Лаб",
        "salary_from": 200_000,
        "salary_to": 320_000,
        "candidate_email": CONTACT_A,
        "candidate_phone": PHONE_A,
    }
    payload.update(overrides)
    return public_application(**payload)  # type: ignore[arg-type]


async def bootstrap(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as session:
        employer = User(kc_sub="emp-1", role="employer", email="boss@lab.test")
        first = User(kc_sub="can-1", role="candidate", email=LOGIN_A)
        second = User(kc_sub="can-2", role="candidate", email="login-b@secret.test")
        third = User(kc_sub="can-3", role="candidate", email=CONTACT_C)
        session.add_all([employer, first, second, third])
        await session.flush()
        session.add(
            Company(
                owner_user_id=employer.id,
                name="ФСП Лаб",
                city="Новосибирск",
                recruiter_contact={},
                benefits=[],
            )
        )
        session.add_all(
            [
                Candidate(
                    user_id=first.id,
                    full_name="Анна Ильина",
                    phone=PHONE_A,
                    contact_email=CONTACT_A,
                    formats=["remote"],
                    status="seeking",
                    visible=True,
                ),
                Candidate(
                    user_id=second.id,
                    full_name="Борис Орлов",
                    phone=PHONE_B,
                    contact_email=CONTACT_B,
                    formats=["remote"],
                    status="seeking",
                    visible=True,
                ),
                Candidate(
                    user_id=third.id,
                    full_name="Скрытый Кандидат",
                    phone=PHONE_C,
                    contact_email=CONTACT_C,
                    formats=["remote"],
                    status="seeking",
                    visible=True,
                ),
            ]
        )
        await session.commit()


async def offer_job(factory: async_sessionmaker[AsyncSession], *, candidate_sub: str = "can-1") -> None:
    async with factory() as session:
        employer = await session.scalar(select(User).where(User.kc_sub == "emp-1"))
        candidate_user = await session.scalar(select(User).where(User.kc_sub == candidate_sub))
        assert employer is not None and candidate_user is not None
        company = await session.scalar(select(Company).where(Company.owner_user_id == employer.id))
        candidate = await session.scalar(select(Candidate).where(Candidate.user_id == candidate_user.id))
        assert company is not None and candidate is not None
        need = Need(
            company_id=company.id,
            title="Backend в процессинг",
            specialization="backend",
            grades=["middle"],
            salary_from=200_000,
            salary_to=320_000,
            formats=["remote"],
            city="Новосибирск",
            must_skills=["go"],
            nice_skills=[],
            description=DESCRIPTION,
            domain="fintech",
            stages=1,
            status="open",
        )
        session.add(need)
        await session.flush()
        session.add(
            Invitation(
                need_id=need.id,
                candidate_id=candidate.id,
                status="sent",
                title="Backend-разработчик",
                message="Предлагаем обсудить роль.",
                salary_from=200_000,
                salary_to=320_000,
            )
        )
        await session.commit()


@pytest.mark.parametrize("state,action", [(state, action) for state in STATES for action in ACTIONS])
def test_application_transitions(state: str, action: str) -> None:
    expected = LEGAL.get((state, action))
    if expected is None:
        with pytest.raises(AppError) as caught:
            next_application_status(state, action)
        assert caught.value.status_code == 409
        assert caught.value.code == "invalid_transition"
        return
    assert next_application_status(state, action) == expected


def test_decline_requires_a_reason() -> None:
    application = Application(vacancy_id=uuid4(), candidate_id=uuid4(), status="sent", message="")
    with pytest.raises(AppError) as caught:
        _apply_transition(application, "decline", reason="  ")
    assert caught.value.status_code == 422
    assert application.status == "sent"


def test_contacts_belong_only_to_the_applicant() -> None:
    own = _application_view(viewer="candidate")
    blob = json.dumps(own, ensure_ascii=False)
    assert own["company_name"] == "ФСП Лаб"
    assert own["title"] == "Backend-разработчик"
    assert own["salary_from"] == 200_000
    assert own["salary_to"] == 320_000
    assert own["status"] == "sent"
    assert "candidate_email" not in own
    assert "candidate_phone" not in own
    assert CONTACT_A not in blob
    assert PHONE_A not in blob

    employer_own = _application_view(viewer="employer")
    employer_other = _application_view(viewer="employer", candidate_email=CONTACT_B, candidate_phone=PHONE_B)
    assert employer_own["candidate_email"] == CONTACT_A
    assert employer_own["candidate_phone"] == PHONE_A
    assert "company_name" not in employer_own
    own_blob = json.dumps(employer_own, ensure_ascii=False)
    other_blob = json.dumps(employer_other, ensure_ascii=False)
    assert CONTACT_B not in own_blob
    assert PHONE_B not in own_blob
    assert CONTACT_A not in other_blob
    assert PHONE_A not in other_blob
    assert applicant_email(CONTACT_A, LOGIN_A) == CONTACT_A
    assert applicant_email(None, LOGIN_A) == LOGIN_A
    assert status_counts(["sent", "sent", "viewed"]) == {"sent": 2, "viewed": 1, "accepted": 0, "declined": 0}


def test_catalog_visibility_and_role_guard() -> None:
    assert vacancy_visible("open", viewer_role="candidate", owns=False)
    assert vacancy_visible("open", viewer_role="employer", owns=False)
    assert not vacancy_visible("closed", viewer_role="candidate", owns=False)
    assert vacancy_visible("closed", viewer_role="employer", owns=True)
    assert not vacancy_visible("closed", viewer_role="employer", owns=False)
    assert resolve_list_role("candidate", None) == "candidate"
    assert resolve_list_role("employer", "employer") == "employer"
    with pytest.raises(AppError) as caught:
        resolve_list_role("candidate", "employer")
    assert caught.value.status_code == 403


def test_salary_grades_and_demo_vacancies() -> None:
    VacancyWrite.model_validate(body())
    VacancyWrite.model_validate(body(description="x" * 50, grades=["junior", "middle"]))
    ensure_vacancy_bounds(200_000, 320_000, ["middle", "senior"])
    missing = body()
    missing.pop("salary_from")
    with pytest.raises(ValidationError):
        VacancyWrite.model_validate(missing)
    missing_to = body()
    missing_to.pop("salary_to")
    with pytest.raises(ValidationError):
        VacancyWrite.model_validate(missing_to)
    with pytest.raises(ValueError, match="верх вилки меньше низа"):
        ensure_vacancy_bounds(300_000, 100_000, ["middle"])
    with pytest.raises(ValueError, match="соседних"):
        ensure_vacancy_bounds(200_000, 320_000, ["intern", "senior"])
    with pytest.raises(ValidationError):
        VacancyWrite.model_validate(body(description="x" * 49))
    with pytest.raises(ValueError, match="неизвестный грейд"):
        check_grades(["wizard"])

    assert len(DEMO_VACANCIES) == 5
    assert {row["specialization"] for row in DEMO_VACANCIES} == {"backend", "frontend", "data_ml", "devops"}
    for row in DEMO_VACANCIES:
        assert row["status"] == "open"
        assert isinstance(row["salary_from"], int)
        assert isinstance(row["salary_to"], int)
        assert row["salary_to"] >= row["salary_from"]
        assert len(row["description"]) >= 50
        check_grades(row["grades"])


async def test_publish_edit_and_open_catalog(api: tuple[AsyncClient, async_sessionmaker[AsyncSession]]) -> None:
    client, factory = api
    await bootstrap(factory)
    created = await client.post("/api/v1/vacancies", headers=EMPLOYER, json=body())
    assert created.status_code == 201, created.text
    vacancy_id = created.json()["id"]
    assert created.json()["salary_from"] == 200_000
    assert created.json()["salary_to"] == 320_000
    assert created.json()["status"] == "open"
    assert CONTACT_A not in created.text

    listed = await client.get("/api/v1/vacancies", headers=CANDIDATE)
    assert listed.status_code == 200, listed.text
    assert listed.json() == []
    closed_door = await client.get(f"/api/v1/vacancies/{vacancy_id}", headers=CANDIDATE)
    assert closed_door.status_code == 404

    await offer_job(factory)
    listed = await client.get("/api/v1/vacancies", headers=CANDIDATE)
    assert vacancy_id in {item["id"] for item in listed.json()}
    assert CONTACT_C not in listed.text
    stranger = await client.get("/api/v1/vacancies", headers=CANDIDATE_B)
    assert stranger.json() == []

    frontend = await client.post(
        "/api/v1/vacancies",
        headers=EMPLOYER,
        json=body(title="Интерфейс кабинета", specialization="frontend", grades=["middle"], domain="edtech"),
    )
    assert frontend.status_code == 201, frontend.text
    frontend_id = frontend.json()["id"]
    matched = await client.get(
        "/api/v1/vacancies",
        headers=CANDIDATE,
        params={"specialization": "frontend", "grade": "middle"},
    )
    assert [item["id"] for item in matched.json()] == [frontend_id]
    junior = await client.get("/api/v1/vacancies", headers=EMPLOYER, params={"grade": "junior"})
    assert junior.json() == []

    async with factory() as session:
        row = await session.get(Vacancy, UUID(vacancy_id))
        assert row is not None
        row.status = "closed"
        await session.commit()

    candidate_list = await client.get("/api/v1/vacancies", headers=CANDIDATE)
    assert vacancy_id not in {item["id"] for item in candidate_list.json()}
    employer_list = await client.get("/api/v1/vacancies", headers=EMPLOYER)
    assert vacancy_id in {item["id"] for item in employer_list.json()}
    hidden = await client.get(f"/api/v1/vacancies/{vacancy_id}", headers=CANDIDATE)
    assert hidden.status_code == 404
    assert hidden.json()["error"]["code"] == "not_found"
    visible = await client.get(f"/api/v1/vacancies/{vacancy_id}", headers=EMPLOYER)
    assert visible.status_code == 200

    edited = await client.put(
        f"/api/v1/vacancies/{vacancy_id}",
        headers=EMPLOYER,
        json=body(title="Новое название", salary_from=210_000, salary_to=330_000),
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["title"] == "Новое название"
    assert edited.json()["salary_from"] == 210_000
    foreign = await client.put(f"/api/v1/vacancies/{vacancy_id}", headers=OTHER_EMPLOYER, json=body(title="Чужое"))
    assert foreign.status_code == 404
    forbidden = await client.put(f"/api/v1/vacancies/{vacancy_id}", headers=CANDIDATE, json=body())
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "forbidden"
    admin = await client.get("/api/v1/vacancies", headers={"x-debug-role": "admin", "x-debug-sub": "adm-1"})
    assert admin.status_code == 403


async def test_apply_disabled(api: tuple[AsyncClient, async_sessionmaker[AsyncSession]]) -> None:
    client, factory = api
    await bootstrap(factory)
    created = await client.post("/api/v1/vacancies", headers=EMPLOYER, json=body())
    assert created.status_code == 201, created.text
    vacancy_id = created.json()["id"]
    applied = await client.post(
        f"/api/v1/vacancies/{vacancy_id}/applications",
        headers=CANDIDATE,
        json={"message": "Готов обсудить задачи"},
    )
    assert applied.status_code == 409, applied.text
    assert applied.json()["error"]["code"] == "applications_disabled"


async def test_validation_errors(api: tuple[AsyncClient, async_sessionmaker[AsyncSession]]) -> None:
    client, factory = api
    await bootstrap(factory)
    missing = body()
    missing.pop("salary_to")
    response = await client.post("/api/v1/vacancies", headers=EMPLOYER, json=missing)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    short = await client.post("/api/v1/vacancies", headers=EMPLOYER, json=body(description="слишком коротко"))
    assert short.status_code == 422
    grades = await client.post("/api/v1/vacancies", headers=EMPLOYER, json=body(grades=["junior", "senior"]))
    assert grades.status_code == 422
    upside_down = await client.post(
        "/api/v1/vacancies",
        headers=EMPLOYER,
        json=body(salary_from=400_000, salary_to=100_000),
    )
    assert upside_down.status_code == 422
    unknown = await client.get("/api/v1/vacancies", headers=CANDIDATE, params={"specialization": "design"})
    assert unknown.status_code == 422
    assert unknown.json()["error"]["code"] == "validation_error"
    denied = await client.post("/api/v1/vacancies", headers=CANDIDATE, json=body())
    assert denied.status_code == 403
