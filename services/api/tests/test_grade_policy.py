"""Grade is not forced down. A neighbor retake is the only grade change, at most once per 90 days."""

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from app.assessment import models as assessment_models  # noqa: F401
from app.assessment.bank import read_task_specs
from app.assessment.scoring import cooldown_active, grade_for, neighbor_grade
from app.company import models as company_models  # noqa: F401
from app.core.auth import Principal, get_principal
from app.core.db import Base, get_session
from app.core.models import User  # noqa: F401
from app.main import app
from app.need import models as need_models  # noqa: F401
from app.profile import models as profile_models  # noqa: F401
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from starlette.requests import Request

ADMIN_DSN = "postgresql+asyncpg://fsp:fsp@127.0.0.1:5432/fsp"
TEST_DSN = os.environ.get("TEST_POSTGRES_DSN", "postgresql+asyncpg://fsp:fsp@127.0.0.1:5432/fsp_g_grade")
NEEDED = {
    "users",
    "companies",
    "needs",
    "candidates",
    "candidate_skills",
    "tasks_bank",
    "attempts",
    "attempt_answers",
    "micro_tasks",
    "micro_answers",
}


def _tables():
    return [table for table in Base.metadata.sorted_tables if table.name in NEEDED]


def _candidate(sub: str) -> dict[str, str]:
    return {"x-debug-role": "candidate", "x-debug-sub": sub}


def _employer(sub: str = "employer-grade") -> dict[str, str]:
    return {"x-debug-role": "employer", "x-debug-sub": sub}


def test_grade_for_never_lowers() -> None:
    assert grade_for(39.99, "middle") == ("middle", False)
    assert grade_for(0, "intern") == ("intern", False)
    assert grade_for(10, "junior", "senior") == ("senior", False)
    assert grade_for(74.99, "lead", "middle") == ("middle", False)
    assert grade_for(75, "junior", "middle") == ("middle", True)
    assert grade_for(100, "intern") == ("intern", True)


def test_cooldown_is_ninety_days_and_first_grade_is_free() -> None:
    now = datetime(2026, 10, 11, tzinfo=UTC)
    assert cooldown_active(None, now) is False
    assert cooldown_active(now - timedelta(days=89, hours=23), now) is True
    assert cooldown_active(now - timedelta(days=90), now) is False
    assert cooldown_active(now - timedelta(days=90) + timedelta(seconds=1), now) is True


def test_neighbor_follows_grade_order() -> None:
    grade = "intern"
    seen = [grade]
    while True:
        try:
            grade = neighbor_grade(grade, "up")
        except ValueError:
            break
        seen.append(grade)
    assert seen == ["intern", "junior", "middle", "senior", "lead"]
    assert neighbor_grade("senior", "down") == "middle"
    with pytest.raises(ValueError):
        neighbor_grade("intern", "down")
    with pytest.raises(ValueError):
        neighbor_grade("lead", "up")


async def _ensure_database() -> None:
    dbname = TEST_DSN.rsplit("/", 1)[1]
    if not dbname.isidentifier():
        raise RuntimeError(f"unsafe database name: {dbname}")
    admin = create_async_engine(ADMIN_DSN, isolation_level="AUTOCOMMIT", poolclass=NullPool, connect_args={"timeout": 2})
    try:
        async with admin.connect() as conn:
            found = await conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": dbname})
            if found.scalar() is None:
                await conn.execute(text(f'CREATE DATABASE "{dbname}"'))
    finally:
        await admin.dispose()


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(TEST_DSN, poolclass=NullPool, connect_args={"timeout": 2})
    try:
        await _ensure_database()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        await engine.dispose()
        pytest.skip(f"PostgreSQL is not available: {exc}")
    async with engine.begin() as conn:
        tables = _tables()
        await conn.run_sync(lambda bind: Base.metadata.drop_all(bind, tables=tables))
        await conn.run_sync(lambda bind: Base.metadata.create_all(bind, tables=tables))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.fixture
async def db_client(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    async def features(_candidate_id: object) -> None:
        return None

    async def hints(_candidate_id: object) -> list[object]:
        return []

    monkeypatch.setattr("app.profile.service.get_candidate_features", features)
    monkeypatch.setattr("app.hints.service.recompute_candidate", hints)

    async def override() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    async def debug_principal(request: Request) -> Principal:
        role = request.headers.get("x-debug-role", "candidate")
        sub = request.headers.get("x-debug-sub", "stub-candidate")
        if role not in {"candidate", "employer", "admin"}:
            role = "candidate"
        return Principal(sub=sub, role=role)

    app.dependency_overrides[get_session] = override
    app.dependency_overrides[get_principal] = debug_principal
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_principal, None)


async def _candidate_row(factory: async_sessionmaker[AsyncSession], sub: str):
    async with factory() as session:
        return (
            await session.execute(
                text(
                    """
                    SELECT c.grade, c.grade_score, c.ready_for_next, c.grade_changed_at, c.last_active_at
                    FROM candidates c
                    JOIN users u ON u.id = c.user_id
                    WHERE u.kc_sub = :sub
                    """
                ),
                {"sub": sub},
            )
        ).one()


async def _finish(client: AsyncClient, headers: dict[str, str], grade: str) -> dict[str, object]:
    created = await client.post(
        "/api/v1/assessment/attempts",
        headers=headers,
        json={"specialization": "backend", "declared_grade": grade},
    )
    assert created.status_code == 201, created.text
    finished = await client.post(f"/api/v1/assessment/attempts/{created.json()['id']}/finish", headers=headers)
    assert finished.status_code == 200, finished.text
    return finished.json()


async def test_failed_attempt_keeps_grade_and_first_assignment_skips_cooldown(
    db_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    headers = _candidate("keep-grade")
    first = await _finish(db_client, headers, "senior")
    assert first["score"] == 0
    assert first["grade"] == "senior"
    assert first["ready_for_next"] is False
    stored = await _candidate_row(session_factory, "keep-grade")
    assert stored.grade == "senior"
    assert stored.grade_changed_at is None

    second = await _finish(db_client, headers, "junior")
    assert second["grade"] == "senior"
    assert second["ready_for_next"] is False
    stored = await _candidate_row(session_factory, "keep-grade")
    assert stored.grade == "senior"
    assert stored.grade_changed_at is None

    denied = await db_client.post("/api/v1/assessment/retake", headers=_candidate("no-grade"), json={"direction": "down"})
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "grade_required"


async def test_retake_moves_one_grade_and_then_cools_down(
    db_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    headers = _candidate("retake-middle")
    await _finish(db_client, headers, "middle")
    opened = await db_client.post("/api/v1/assessment/retake", headers=headers, json={"direction": "down"})
    assert opened.status_code == 201, opened.text
    body = opened.json()
    assert body["declared_grade"] == "junior"
    finished = await db_client.post(f"/api/v1/assessment/attempts/{body['id']}/finish", headers=headers)
    assert finished.status_code == 200, finished.text
    assert finished.json()["grade"] == "junior"
    assert finished.json()["ready_for_next"] is False
    stored = await _candidate_row(session_factory, "retake-middle")
    assert stored.grade == "junior"
    assert stored.grade_changed_at is not None

    blocked = await db_client.post("/api/v1/assessment/retake", headers=headers, json={"direction": "up"})
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "grade_cooldown"

    async with session_factory() as session:
        await session.execute(
            text(
                """
                UPDATE candidates AS c
                SET grade_changed_at = NOW() - INTERVAL '91 days'
                FROM users u
                WHERE u.id = c.user_id AND u.kc_sub = :sub
                """
            ),
            {"sub": "retake-middle"},
        )
        await session.commit()
    again = await db_client.post("/api/v1/assessment/retake", headers=headers, json={"direction": "up"})
    assert again.status_code == 201, again.text
    assert again.json()["declared_grade"] == "middle"


async def test_retake_stops_at_the_ends_of_the_scale(db_client: AsyncClient) -> None:
    lead = _candidate("edge-lead")
    await _finish(db_client, lead, "lead")
    up = await db_client.post("/api/v1/assessment/retake", headers=lead, json={"direction": "up"})
    assert up.status_code == 400
    assert up.json()["error"]["code"] == "grade_boundary"

    intern = _candidate("edge-intern")
    await _finish(db_client, intern, "intern")
    down = await db_client.post("/api/v1/assessment/retake", headers=intern, json={"direction": "down"})
    assert down.status_code == 400
    assert down.json()["error"]["code"] == "grade_boundary"


async def test_confident_pass_marks_ready_without_raising_grade(db_client: AsyncClient) -> None:
    headers = _candidate("ready-next")
    created = await db_client.post(
        "/api/v1/assessment/attempts",
        headers=headers,
        json={"specialization": "backend", "declared_grade": "middle"},
    )
    assert created.status_code == 201, created.text
    attempt_id = created.json()["id"]
    mcq = [spec for spec in read_task_specs() if spec.specialization == "backend" and spec.kind == "mcq"]
    assert len(mcq) == 9
    for spec in mcq:
        saved = await db_client.post(
            f"/api/v1/assessment/attempts/{attempt_id}/answers",
            headers=headers,
            json={"task_id": spec.id, "answer": spec.answer},
        )
        assert saved.status_code == 200, saved.text
    finished = await db_client.post(f"/api/v1/assessment/attempts/{attempt_id}/finish", headers=headers)
    assert finished.status_code == 200, finished.text
    assert finished.json()["score"] == 75
    assert finished.json()["grade"] == "middle"
    assert finished.json()["ready_for_next"] is True


async def test_micro_tasks_are_listed_once_and_refresh_activity(
    db_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    headers = _candidate("micro-person")
    listed = await db_client.get("/api/v1/assessment/micro-tasks", headers=headers)
    assert listed.status_code == 200, listed.text
    titles = [item["title"] for item in listed.json()]
    assert titles == ["Разберите гонку в кэше", "Как бы вы деградировали Kafka-консьюмер"]
    again = await db_client.get("/api/v1/assessment/micro-tasks", headers=headers)
    assert [item["title"] for item in again.json()] == titles

    missing = await db_client.post(
        "/api/v1/assessment/micro-tasks",
        headers=_employer(),
        json={"title": "Разберите таймаут", "body": "Коротко.", "need_id": str(uuid4())},
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "need_not_found"

    created = await db_client.post(
        "/api/v1/assessment/micro-tasks",
        headers=_employer(),
        json={"title": "Разберите таймаут", "body": "Что делаете, когда ручка не успевает."},
    )
    assert created.status_code == 201, created.text
    forbidden = await db_client.post(
        "/api/v1/assessment/micro-tasks",
        headers=headers,
        json={"title": "Нет прав", "body": "Кандидат не создаёт задания."},
    )
    assert forbidden.status_code == 403

    visible = await db_client.get("/api/v1/assessment/micro-tasks", headers=headers)
    assert [item["title"] for item in visible.json()] == [*titles, "Разберите таймаут"]
    task_id = visible.json()[0]["id"]
    short = await db_client.post(
        f"/api/v1/assessment/micro-tasks/{task_id}/answer",
        headers=headers,
        json={"answer": "слишком коротко"},
    )
    assert short.status_code == 422
    answered = await db_client.post(
        f"/api/v1/assessment/micro-tasks/{task_id}/answer",
        headers=headers,
        json={"answer": "Кэш читают и пишут без лока, поэтому значение теряется."},
    )
    assert answered.status_code == 201, answered.text
    stored = await _candidate_row(session_factory, "micro-person")
    assert stored.last_active_at is not None
    left = await db_client.get("/api/v1/assessment/micro-tasks", headers=headers)
    assert task_id not in [item["id"] for item in left.json()]
    assert len(left.json()) == 2
    duplicate = await db_client.post(
        f"/api/v1/assessment/micro-tasks/{task_id}/answer",
        headers=headers,
        json={"answer": "Повторный ответ на то же короткое задание."},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "micro_answered"
    unknown = await db_client.post(
        f"/api/v1/assessment/micro-tasks/{uuid4()}/answer",
        headers=headers,
        json={"answer": "Такого задания в списке нет, ответ некуда класть."},
    )
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "micro_not_found"
