import asyncio
import os
import subprocess
from uuid import uuid4

import httpx
import pytest
from app.core import db
from app.core.db import EMBEDDING_DIM, Base
from app.core.settings import get_settings
from app.embeddings.service import embed, reset_model
from app.llm.service import extract, sanitize
from app.main import app
from app.profile.models import EvidenceUnit
from app.profile.service import ensure_candidate, get_candidate_features
from httpx import ASGITransport, AsyncClient
from openai import APITimeoutError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

TEST_DSN = "postgresql+asyncpg://fsp:fsp@127.0.0.1:55432/fsp"
_SCHEMA = False


def _ensure_container() -> None:
    name = "fsp-agent-b-pg"
    inspected = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", name],
        capture_output=True,
        text=True,
    )
    if inspected.returncode != 0:
        subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                name,
                "-e",
                "POSTGRES_USER=fsp",
                "-e",
                "POSTGRES_PASSWORD=fsp",
                "-e",
                "POSTGRES_DB=fsp",
                "-p",
                "55432:5432",
                "pgvector/pgvector:pg16",
            ],
            check=True,
        )
    elif inspected.stdout.strip() != "true":
        subprocess.run(["docker", "start", name], check=True)


def _import_models() -> None:
    import app.assessment.models  # noqa: F401
    import app.chat.models  # noqa: F401
    import app.company.models  # noqa: F401
    import app.core.models  # noqa: F401
    import app.invitation.models  # noqa: F401
    import app.need.models  # noqa: F401
    import app.profile.models  # noqa: F401
    import app.resume.models  # noqa: F401


async def prepare_database() -> None:
    """Bind a fresh engine to the current event loop. Schema is created once."""
    global _SCHEMA
    _ensure_container()
    os.environ["POSTGRES_DSN"] = TEST_DSN
    get_settings.cache_clear()
    db.engine = create_async_engine(TEST_DSN, poolclass=NullPool)
    db.SessionLocal = async_sessionmaker(db.engine, expire_on_commit=False)
    if _SCHEMA:
        return
    last_error: Exception | None = None
    for _ in range(40):
        try:
            async with db.engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            break
        except Exception as exc:
            last_error = exc
            await asyncio.sleep(0.5)
    else:
        raise RuntimeError(f"postgres is not ready: {last_error}")
    _import_models()
    async with db.engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    _SCHEMA = True


async def truncate_database() -> None:
    async with db.engine.begin() as conn:
        names = ", ".join(table.name for table in reversed(Base.metadata.sorted_tables))
        await conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))


def headers(sub: str = "candidate-b") -> dict[str, str]:
    return {"x-debug-role": "candidate", "x-debug-sub": sub, "x-debug-email": f"{sub}@example.com"}


@pytest.fixture(autouse=True)
def _llm_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_ENABLED", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
async def database():
    await prepare_database()
    await truncate_database()
    yield
    await db.engine.dispose()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


@pytest.fixture
def fake_embed(monkeypatch: pytest.MonkeyPatch):
    async def _embed(texts: list[str], prefix: str = "passage") -> list[list[float]]:
        return [[0.25] * EMBEDDING_DIM for _ in texts]

    monkeypatch.setattr("app.embeddings.service.embed", _embed)


@pytest.fixture
def hints(monkeypatch: pytest.MonkeyPatch):
    calls: list = []

    async def _recompute(candidate_id):
        calls.append(candidate_id)
        return []

    monkeypatch.setattr("app.hints.service.recompute_candidate", _recompute)
    return calls


def test_sanitize_strips_invisible_and_caps_length() -> None:
    assert sanitize("Kafka\u200b stream") == "Kafka stream"
    assert len(sanitize("A" * 25_000)) == 20_000
    assert "TAIL" not in sanitize(("A" * 20_000) + "TAIL")


async def test_extract_disabled_keeps_phase0_shape() -> None:
    resume = await extract("resume", "строил антифрод")
    assert resume == {"experiences": [], "skills": [], "projects": []}
    unit = await extract("evidence_unit", "строил антифрод на Kafka")
    assert unit["evidence_span"] in "строил антифрод на Kafka"
    assert unit["role"] == "participant"


async def test_extract_retries_and_drops_unquoted_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_ENABLED", "true")
    get_settings.cache_clear()
    calls = {"n": 0}

    async def flaky(schema_name: str, text: str) -> dict:
        calls["n"] += 1
        if calls["n"] < 3:
            raise APITimeoutError(httpx.Request("POST", "https://llm.example/v1/chat/completions"))
        return {
            "experiences": [
                {"company": "Nope", "role": "x", "description": "y", "evidence_span": "нет в тексте"},
                {"company": "Ромашка", "role": "backend", "description": "антифрод", "evidence_span": "антифрод"},
            ],
            "skills": [],
            "projects": [],
        }

    monkeypatch.setattr("app.llm.service._once", flaky)
    result = await extract("resume", "делал антифрод в команде")
    assert calls["n"] == 3
    assert result["experiences"] == [
        {"company": "Ромашка", "role": "backend", "description": "антифрод", "evidence_span": "антифрод"}
    ]
    monkeypatch.setenv("LLM_ENABLED", "false")
    get_settings.cache_clear()


async def test_embed_prefixes_batches_and_loads_model_once(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_model()
    seen: list[list[str]] = []

    class FakeModel:
        def encode(self, texts, batch_size=32, normalize_embeddings=True):
            assert batch_size == 32
            assert normalize_embeddings is True
            seen.append(list(texts))
            return [[0.1] * EMBEDDING_DIM for _ in texts]

    calls = {"n": 0}

    def factory(name: str) -> FakeModel:
        calls["n"] += 1
        assert "e5" in name
        return FakeModel()

    monkeypatch.setattr("app.embeddings.service._import_sentence_transformer", lambda: factory)
    first = await embed(["kafka", "go"], prefix="passage")
    second = await embed(["поиск"], prefix="query")
    assert len(second) == 1 and len(second[0]) == EMBEDDING_DIM
    assert calls["n"] == 1
    assert len(first) == 2 and len(first[0]) == EMBEDDING_DIM
    assert seen[0] == ["passage: kafka", "passage: go"]
    assert seen[1] == ["query: поиск"]
    assert await embed([]) == []
    reset_model()


async def test_embed_without_library_is_zero_vector(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_model()

    def boom() -> object:
        raise ImportError("sentence-transformers is absent")

    monkeypatch.setattr("app.embeddings.service._import_sentence_transformer", boom)
    vectors = await embed(["kafka"])
    assert vectors == [[0.0] * EMBEDDING_DIM]
    reset_model()


async def test_profile_pool_projects_and_features(
    database, client: AsyncClient, fake_embed, hints
) -> None:
    created = await client.get("/api/v1/me", headers=headers())
    assert created.status_code == 200
    me = created.json()
    assert me["candidate_id"]
    assert me["role"] == "candidate"

    profile = await client.get("/api/v1/candidates/me", headers=headers())
    assert profile.status_code == 200
    body = profile.json()
    assert body["id"] == me["candidate_id"]
    assert body["in_pool_eligible"] is False
    assert body["display_name"] == ""

    salary_only = await client.put("/api/v1/candidates/me", headers=headers(), json={"min_salary": 180000})
    assert salary_only.status_code == 200
    assert salary_only.json()["in_pool_eligible"] is False

    named = await client.put(
        "/api/v1/candidates/me",
        headers=headers(),
        json={
            "full_name": "Алексей Кузнецов",
            "min_salary": 180000,
            "formats": ["remote"],
            "city": "Новосибирск",
            "specialization": "backend",
            "status": "seeking",
            "liked_skills": ["K8s"],
            "liked_domains": ["Финтех"],
        },
    )
    assert named.status_code == 200
    profile_body = named.json()
    assert profile_body["in_pool_eligible"] is True
    assert profile_body["display_name"] == "Алексей К."
    assert profile_body["liked_skills"] == ["kubernetes"]
    assert profile_body["liked_domains"] == ["fintech"]

    unknown = await client.put(
        "/api/v1/candidates/me",
        headers=headers(),
        json={"liked_skills": ["not-a-real-skill"]},
    )
    assert unknown.status_code == 400
    assert unknown.json()["error"]["code"] == "unknown_skill"

    forbidden = await client.get("/api/v1/candidates/me", headers={"x-debug-role": "employer", "x-debug-sub": "boss"})
    assert forbidden.status_code == 403

    project = await client.post(
        "/api/v1/candidates/me/projects",
        headers=headers(),
        json={
            "task": "Собрал антифрод на Kafka",
            "role": "owner",
            "skills": ["Kafka", "k8s"],
            "scale": "3k rps",
            "outcome": "снизили фрод",
            "date": "2024-05-01T00:00:00Z",
            "url": "https://example.com/antifraud",
        },
    )
    assert project.status_code == 201
    created_project = project.json()
    assert created_project["skills"] == ["kafka", "kubernetes"]
    assert created_project["source"] == "self"
    assert created_project["role"] == "owner"
    assert hints

    features = await get_candidate_features(profile_body["id"])
    assert features.full_name == "Алексей Кузнецов"
    assert features.display_name == "Алексей К."
    assert any(skill.skill_id == "kafka" and skill.source == "project" for skill in features.skills)
    assert len(features.evidence) == 1
    unit = features.evidence[0]
    assert unit.origin == "project"
    assert unit.trust == 0.35
    assert unit.role == "owner"
    assert "kafka" in unit.skills
    assert unit.embedding is not None and len(unit.embedding) == EMBEDDING_DIM
    assert unit.embedding[0] == 0.25
    assert unit.evidence_span

    zero_salary = await client.put(
        "/api/v1/candidates/me",
        headers=headers(),
        json={"min_salary": 0, "formats": ["office"]},
    )
    assert zero_salary.json()["in_pool_eligible"] is True

    cleared = await client.put("/api/v1/candidates/me", headers=headers(), json={"formats": []})
    assert cleared.json()["in_pool_eligible"] is False

    listed = await client.get("/api/v1/candidates/me/projects", headers=headers())
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    removed = await client.delete(f"/api/v1/candidates/me/projects/{created_project['id']}", headers=headers())
    assert removed.status_code == 204
    empty = await client.get("/api/v1/candidates/me/projects", headers=headers())
    assert empty.json() == []
    after_delete = await get_candidate_features(profile_body["id"])
    assert after_delete.evidence == []


async def test_unquoted_extraction_is_not_stored(database, client: AsyncClient, fake_embed, hints, monkeypatch) -> None:
    async def bad_extract(schema_name: str, text: str) -> dict:
        return {
            "task": "выдумано",
            "skills": ["kafka"],
            "role": "owner",
            "domain": None,
            "date": None,
            "evidence_span": "этой цитаты нет",
        }

    monkeypatch.setattr("app.llm.service.extract", bad_extract)
    created = await client.post(
        "/api/v1/candidates/me/projects",
        headers=headers("no-quote"),
        json={"task": "реальный текст проекта", "role": "contributor", "skills": ["python"]},
    )
    assert created.status_code == 201
    profile = await client.get("/api/v1/candidates/me", headers=headers("no-quote"))
    features = await get_candidate_features(profile.json()["id"])
    assert features.evidence == []
    assert hints


async def test_fsp_link_caps_at_three_and_sets_source(database, client: AsyncClient, fake_embed, hints, tmp_path) -> None:
    payload = {
        "by_sub": {
            "fsp-user": [
                {"discipline": "алгоритмы", "event": "Кубок", "place": 1, "year": 2024, "skills": ["python"]},
                {"discipline": "backend", "event": "Хакатон", "place": 2, "year": 2023, "skills": ["kafka"]},
                {"discipline": "данные", "event": "Финал", "place": 3, "year": 2022, "skills": []},
                {"discipline": "лишнее", "event": "Четвёртое", "place": 4, "year": 2021, "skills": ["go"]},
            ],
            "other": [{"discipline": "go", "event": "Чужое", "place": 1, "year": 2020, "skills": ["go"]}],
        }
    }
    path = tmp_path / "fsp.json"
    path.write_text(__import__("json").dumps(payload), encoding="utf-8")
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("app.profile.fsp.achievements_path", lambda: path)
    try:
        linked = await client.post("/api/v1/candidates/me/fsp-link", headers=headers("fsp-user"))
        assert linked.status_code == 200
        body = linked.json()
        assert len(body["fsp_achievements"]) == 3
        assert {item["event"] for item in body["fsp_achievements"]} == {"Кубок", "Хакатон", "Финал"}
        sources = {(item["skill_id"], item["source"]) for item in body["skills"]}
        assert ("python", "fsp_id") in sources
        assert ("kafka", "fsp_id") in sources
        assert ("algorithms", "fsp_id") in sources
        features = await get_candidate_features(body["id"])
        fsp_units = [item for item in features.evidence if item.origin == "fsp"]
        assert len(fsp_units) == 3
        assert {item.trust for item in fsp_units} == {1.0}
        again = await client.post("/api/v1/candidates/me/fsp-link", headers=headers("fsp-user"))
        assert len(again.json()["fsp_achievements"]) == 3
    finally:
        monkeypatch.undo()


async def test_empty_fsp_seed_links_nothing(database, client: AsyncClient, fake_embed, hints) -> None:
    linked = await client.post("/api/v1/candidates/me/fsp-link", headers=headers("empty-fsp"))
    assert linked.status_code == 200
    assert linked.json()["fsp_achievements"] == []


async def test_grade_and_settings_roundtrip(database, client: AsyncClient) -> None:
    profile = await client.get("/api/v1/candidates/me", headers=headers("grade-user"))
    candidate_id = profile.json()["id"]
    async with db.SessionLocal() as session:
        from app.profile.models import Candidate

        candidate = await session.get(Candidate, candidate_id)
        assert candidate is not None
        candidate.grade = "middle"
        candidate.grade_score = 81
        candidate.category_rank = 4
        candidate.category_size = 100
        candidate.ready_for_next = True
        await session.commit()
    grade = await client.get("/api/v1/candidates/me/grade", headers=headers("grade-user"))
    assert grade.status_code == 200
    assert grade.json()["grade"] == "middle"
    assert grade.json()["score"] == 81
    assert grade.json()["rank"] == 4
    company_id = str(uuid4())
    settings = await client.put(
        "/api/v1/candidates/me/settings",
        headers=headers("grade-user"),
        json={"visible": False, "hidden_company_ids": [company_id]},
    )
    assert settings.status_code == 200
    assert settings.json()["visible"] is False
    assert settings.json()["hidden_company_ids"] == [company_id]
    fetched = await client.get("/api/v1/candidates/me/settings", headers=headers("grade-user"))
    assert fetched.json()["visible"] is False


async def test_missing_candidate_features_are_empty(database) -> None:
    features = await get_candidate_features(uuid4())
    assert features.full_name == ""
    assert features.evidence == []
    assert features.visible is False


async def test_ensure_candidate_hook_creates_row(database) -> None:
    from app.core.models import User

    async with db.SessionLocal() as session:
        user = User(kc_sub="hook-user", role="candidate", email="hook@example.com")
        session.add(user)
        await session.commit()
        user_id = user.id
    candidate_id = await ensure_candidate(user_id)
    again = await ensure_candidate(user_id)
    assert candidate_id == again
    async with db.SessionLocal() as session:
        rows = list(await session.scalars(select(EvidenceUnit)))
    assert rows == []
