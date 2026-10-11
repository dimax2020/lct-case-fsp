"""CAT attempt flow against Postgres when it is available."""

import os
from collections.abc import AsyncIterator, Iterator

import pytest
from app.assessment import models as assessment_models  # noqa: F401
from app.core.auth import Principal, get_principal
from app.core.db import Base, get_session
from app.core.models import User  # noqa: F401
from app.main import app
from app.profile import models as profile_models  # noqa: F401
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from starlette.requests import Request

ADMIN_DSN = "postgresql+asyncpg://fsp:fsp@127.0.0.1:5432/fsp"
TEST_DSN = os.environ.get("TEST_POSTGRES_DSN", "postgresql+asyncpg://fsp:fsp@127.0.0.1:5432/fsp_c_cat")
NEEDED = {"users", "candidates", "candidate_skills", "tasks_bank", "attempts", "attempt_answers", "cat_exposure"}


def _tables():
    return [table for table in Base.metadata.sorted_tables if table.name in NEEDED]


@pytest.fixture(autouse=True)
def _cat_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASSESSMENT_ENGINE", "cat")


@pytest.fixture(autouse=True)
def _debug_auth() -> Iterator[None]:
    async def debug_principal(request: Request) -> Principal:
        return Principal(sub=request.headers.get("x-debug-sub", "cat-user"), role="candidate")

    app.dependency_overrides[get_principal] = debug_principal
    yield
    app.dependency_overrides.pop(get_principal, None)


async def _ensure_database() -> None:
    dbname = TEST_DSN.rsplit("/", 1)[1]
    admin = create_async_engine(ADMIN_DSN, isolation_level="AUTOCOMMIT", poolclass=NullPool, connect_args={"timeout": 2})
    try:
        async with admin.connect() as conn:
            found = await conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": dbname})
            if found.scalar() is None:
                await conn.execute(text(f'CREATE DATABASE "{dbname}"'))
    finally:
        await admin.dispose()


@pytest.fixture
async def db_client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
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

    async def features(_candidate_id: object) -> None:
        return None

    async def hints(_candidate_id: object) -> list[object]:
        return []

    monkeypatch.setattr("app.profile.service.get_candidate_features", features)
    monkeypatch.setattr("app.hints.service.recompute_candidate", hints)

    async def override() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    app.dependency_overrides.pop(get_session, None)
    await engine.dispose()


async def test_cat_session_answers_and_finishes(db_client: AsyncClient) -> None:
    headers = {"X-Debug-Role": "candidate", "X-Debug-Sub": "cat-live"}
    created = await db_client.post(
        "/api/v1/assessment/attempts",
        headers=headers,
        json={"specialization": "backend", "declared_grade": "middle"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["engine"] == "cat"
    assert body["task"]["id"]
    assert body["task"]["format"]
    assert body["progress"]["total"] == 20
    attempt_id = body["id"]

    for _ in range(25):
        view = (await db_client.get(f"/api/v1/assessment/attempts/{attempt_id}", headers=headers)).json()
        if view.get("result") or view.get("finished_at") or not view.get("task"):
            break
        task = view["task"]
        payload: dict[str, object] = {"task_id": task["id"], "skip": False}
        if task.get("format") == "MSQ" and task.get("options"):
            payload["answer"] = ",".join(item["id"] for item in task["options"][:1])
        elif task.get("kind") == "mcq" and task.get("options"):
            payload["answer"] = task["options"][0]["id"]
        elif task.get("format") == "CODE":
            payload["code"] = "def revenue_by_city(records):\n    return {}"
            payload["language"] = "python"
        else:
            payload["answer"] = "кэш транзакция sql 15 git reset"
        saved = await db_client.post(f"/api/v1/assessment/attempts/{attempt_id}/answers", headers=headers, json=payload)
        assert saved.status_code == 200, saved.text
        if saved.json().get("result"):
            body = saved.json()
            break
    else:
        finished = await db_client.post(f"/api/v1/assessment/attempts/{attempt_id}/finish", headers=headers)
        assert finished.status_code == 200, finished.text
        body = {"result": finished.json()}

    final = (await db_client.get(f"/api/v1/assessment/attempts/{attempt_id}", headers=headers)).json()
    result = final.get("result")
    if result is None:
        finished = await db_client.post(f"/api/v1/assessment/attempts/{attempt_id}/finish", headers=headers)
        assert finished.status_code == 200, finished.text
        result = finished.json()
    assert result["grade"] in {"intern", "junior", "middle", "senior", "lead"}
    assert result["theta"] is not None
    assert result["decision"] in {"passed", "above", "borderline", "below"}
    gate = await db_client.get("/api/v1/assessment/eligibility", headers=headers)
    assert gate.status_code == 200
    assert gate.json()["can_start"] is False
    assert gate.json()["reason"] == "retry_cooldown"
