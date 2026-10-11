import json
import os
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from app.assessment import models as assessment_models  # noqa: F401
from app.assessment.bank import read_task_specs
from app.assessment.piston import CPU_LIMIT_MS, MEMORY_LIMIT_BYTES, normalize_output
from app.assessment.scoring import GradedAnswer, GradedTask, grade_for, score_attempt
from app.assessment.service import run_code, to_public
from app.core.auth import Principal, get_principal
from app.core.db import Base, get_session
from app.core.errors import AppError
from app.core.models import User  # noqa: F401
from app.core.settings import get_settings
from app.main import app
from app.profile import models as profile_models  # noqa: F401
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from starlette.requests import Request

ADMIN_DSN = "postgresql+asyncpg://fsp:fsp@127.0.0.1:5432/fsp"
TEST_DSN = os.environ.get("TEST_POSTGRES_DSN", "postgresql+asyncpg://fsp:fsp@127.0.0.1:5432/fsp_c_assessment")
NEEDED = {"users", "candidates", "candidate_skills", "tasks_bank", "attempts", "attempt_answers"}


def _tables():
    return [table for table in Base.metadata.sorted_tables if table.name in NEEDED]


def _candidate(sub: str) -> dict[str, str]:
    return {"X-Debug-Role": "candidate", "X-Debug-Sub": sub}


def _admin() -> dict[str, str]:
    return {"X-Debug-Role": "admin", "X-Debug-Sub": "admin-assessment"}


@pytest.fixture(autouse=True)
def _yaml_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASSESSMENT_ENGINE", "yaml")


@pytest.fixture(autouse=True)
def _debug_auth() -> Iterator[None]:
    async def debug_principal(request: Request) -> Principal:
        role = request.headers.get("x-debug-role", "candidate")
        sub = request.headers.get("x-debug-sub", "stub-candidate")
        email = request.headers.get("x-debug-email")
        if role not in {"candidate", "employer", "admin"}:
            role = "candidate"
        return Principal(sub=sub, role=role, email=email)

    app.dependency_overrides[get_principal] = debug_principal
    yield
    app.dependency_overrides.pop(get_principal, None)


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


@pytest.fixture
def piston_on(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    monkeypatch.setenv("PISTON_ENABLED", "true")
    monkeypatch.setenv("PISTON_URL", "http://piston.test")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def piston_exec(piston_on: None, monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    async def fake(payload: dict[str, object]) -> dict[str, object]:
        calls.append(payload)
        code = payload["files"][0]["content"]  # type: ignore[index]
        proc = subprocess.run(
            [sys.executable, "-c", str(code)],
            input=str(payload.get("stdin") or ""),
            text=True,
            capture_output=True,
            timeout=3,
            check=False,
        )
        return {
            "language": payload["language"],
            "version": "3.12.0",
            "run": {
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "code": proc.returncode,
                "signal": None,
                "output": proc.stdout + proc.stderr,
            },
        }

    monkeypatch.setattr("app.assessment.piston.post_execute", fake)
    return calls


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

    app.dependency_overrides[get_session] = override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    app.dependency_overrides.pop(get_session, None)


def test_task_bank_and_python_solutions() -> None:
    specs = read_task_specs()
    assert len(specs) == 48
    for name in ("backend", "frontend", "data_ml", "devops"):
        group = [spec for spec in specs if spec.specialization == name]
        assert len(group) == 12
        assert sum(spec.kind == "mcq" for spec in group) == 9
        assert sum(spec.kind == "code" for spec in group) == 3
        assert {spec.difficulty for spec in group} >= {1, 2, 3, 4, 5}
    for spec in specs:
        if spec.kind != "code":
            continue
        assert spec.languages == ("python", "go")
        for case in (*spec.tests_public, *spec.tests_hidden):  # type: ignore[misc]
            proc = subprocess.run(
                [sys.executable, "-c", spec.solutions["python"]],
                input=case["stdin"],
                text=True,
                capture_output=True,
                timeout=3,
                check=False,
            )
            assert proc.returncode == 0, spec.id
            assert normalize_output(proc.stdout) == normalize_output(case["expected"]), spec.id


def test_public_task_hides_answer_and_hidden_tests() -> None:
    for spec in read_task_specs():
        data = to_public(spec).model_dump()
        assert "answer" not in data
        assert "tests_hidden" not in data
        assert "solutions" not in data
        if spec.kind == "mcq":
            assert data["tests_public"] is None
            continue
        dumped = json.dumps(data)
        for case in spec.tests_hidden or ():
            for token in (case["stdin"].strip(), case["expected"].strip()):
                if len(token) >= 3:
                    assert token not in dumped, spec.id


def test_grade_thresholds() -> None:
    assert grade_for(39.99, "middle") == ("middle", False)
    assert grade_for(40, "middle") == ("middle", False)
    assert grade_for(74, "middle") == ("middle", False)
    assert grade_for(75, "middle") == ("middle", True)
    assert grade_for(100, "lead") == ("lead", True)
    assert grade_for(0, "intern") == ("intern", False)


def test_skill_scores_follow_task_tags() -> None:
    tasks = [
        GradedTask(id="a", kind="mcq", skills=("python",), answer="a"),
        GradedTask(id="b", kind="mcq", skills=("python", "go"), answer="b"),
    ]
    answers = [
        GradedAnswer(task_id="a", answer="a", skipped=False, verdict="OK", passed=1, total=1),
        GradedAnswer(task_id="b", answer="x", skipped=False, verdict="WRONG_ANSWER", passed=0, total=1),
    ]
    score, skills = score_attempt(tasks, answers)
    assert score == 50
    assert skills["python"] == 50
    assert skills["go"] == 0
    pending = [GradedAnswer(task_id="a", answer=None, skipped=False, verdict="PENDING", passed=0, total=2)]
    pending_score, _ = score_attempt(tasks[:1], pending)
    assert pending_score == 0


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"compile": {"code": 1, "stderr": "syntax error", "stdout": "", "signal": None}}, "COMPILE_ERROR"),
        ({"run": {"code": None, "signal": "SIGKILL", "stdout": "", "stderr": "", "output": ""}}, "TIME_LIMIT"),
        ({"run": {"code": 1, "signal": None, "stdout": "", "stderr": "fatal: out of memory", "output": ""}}, "MEMORY_LIMIT"),
        ({"run": {"code": 1, "signal": None, "stdout": "", "stderr": "panic: boom", "output": ""}}, "RUNTIME_ERROR"),
        ({"run": {"code": 0, "signal": None, "stdout": "nope\n", "stderr": "", "output": "nope\n"}}, "WRONG_ANSWER"),
    ],
)
async def test_piston_verdicts(piston_on: None, monkeypatch: pytest.MonkeyPatch, payload: dict, expected: str) -> None:
    async def fake(_payload: dict) -> dict:
        return payload

    monkeypatch.setattr("app.assessment.piston.post_execute", fake)
    spec = next(item for item in read_task_specs() if item.kind == "code")
    result = await run_code(spec.id, "package main", "go", True)
    assert result.verdict == expected
    assert result.passed == 0
    assert result.total == len(spec.tests_hidden or ())


async def test_hidden_cases_and_limits(piston_on: None, monkeypatch: pytest.MonkeyPatch) -> None:
    spec = next(item for item in read_task_specs() if item.id == "backend-code-01")
    seen: list[str] = []

    async def fake(payload: dict) -> dict:
        seen.append(str(payload["stdin"]))
        assert payload["language"] == "go"
        assert payload["files"][0]["name"] == "main.go"  # type: ignore[index]
        assert payload["run_cpu_time"] == CPU_LIMIT_MS
        assert payload["compile_cpu_time"] == CPU_LIMIT_MS
        assert payload["run_memory_limit"] == MEMORY_LIMIT_BYTES
        assert payload["compile_memory_limit"] == MEMORY_LIMIT_BYTES
        assert payload["version"] == "*"
        return {"run": {"code": 0, "signal": None, "stdout": "0\n", "stderr": ""}}

    monkeypatch.setattr("app.assessment.piston.post_execute", fake)
    public = await run_code(spec.id, "package main", "Golang", False)
    assert [case["stdin"] for case in spec.tests_public or ()] == seen
    assert public.total == len(spec.tests_public or ())
    seen.clear()
    hidden = await run_code(spec.id, "package main", "go", True)
    assert [case["stdin"] for case in spec.tests_hidden or ()] == seen
    assert hidden.total == len(spec.tests_hidden or ())
    assert hidden.verdict == "WRONG_ANSWER"


async def test_time_limit_beats_a_passed_case(piston_on: None, monkeypatch: pytest.MonkeyPatch) -> None:
    spec = next(item for item in read_task_specs() if item.id == "backend-code-01")
    hidden = list(spec.tests_hidden or ())

    async def fake(payload: dict) -> dict:
        if payload["stdin"] == hidden[0]["stdin"]:
            return {"run": {"code": 0, "signal": None, "stdout": hidden[0]["expected"], "stderr": ""}}
        return {"run": {"code": None, "signal": "SIGKILL", "stdout": "", "stderr": ""}}

    monkeypatch.setattr("app.assessment.piston.post_execute", fake)
    result = await run_code(spec.id, "x", "python", True)
    assert result.passed == 1
    assert result.total == 2
    assert result.verdict == "TIME_LIMIT"


async def test_piston_disabled_or_down_is_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = next(item for item in read_task_specs() if item.kind == "code")
    monkeypatch.setenv("PISTON_ENABLED", "false")
    get_settings.cache_clear()
    called = False

    async def fake(_payload: dict) -> dict:
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr("app.assessment.piston.post_execute", fake)
    pending = await run_code(spec.id, "print(1)", "python", True)
    assert pending.verdict == "PENDING"
    assert pending.total == len(spec.tests_hidden or ())
    assert called is False

    monkeypatch.setenv("PISTON_ENABLED", "true")
    get_settings.cache_clear()

    async def down(_payload: dict) -> dict:
        raise RuntimeError("piston down")

    monkeypatch.setattr("app.assessment.piston.post_execute", down)
    failed = await run_code(spec.id, "print(1)", "python", False)
    assert failed.verdict == "PENDING"
    get_settings.cache_clear()


async def test_unknown_language_is_rejected(piston_on: None) -> None:
    spec = next(item for item in read_task_specs() if item.kind == "code")
    with pytest.raises(AppError) as caught:
        await run_code(spec.id, "print(1)", "javascript", False)
    assert caught.value.status_code == 400
    assert caught.value.code == "language_not_allowed"


@pytest.mark.integration
async def test_real_piston_python_solution(monkeypatch: pytest.MonkeyPatch) -> None:
    url = os.environ.get("PISTON_URL")
    if not url:
        pytest.skip("PISTON_URL is not set")
    monkeypatch.setenv("PISTON_ENABLED", "true")
    monkeypatch.setenv("PISTON_URL", url)
    get_settings.cache_clear()
    spec = next(item for item in read_task_specs() if item.kind == "code")
    try:
        result = await run_code(spec.id, spec.solutions["python"], "python", True)
    finally:
        get_settings.cache_clear()
    assert result.verdict == "OK"
    assert result.passed == result.total
    assert result.total == len(spec.tests_hidden or ())


async def test_employer_cannot_start_attempt(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/assessment/attempts",
        headers={"X-Debug-Role": "employer", "X-Debug-Sub": "employer-1"},
        json={"specialization": "backend", "declared_grade": "middle"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_full_attempt_with_skip_return_and_mocked_piston(
    db_client: AsyncClient,
    piston_exec: list[dict[str, object]],
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    async def features(candidate_id: object) -> dict[str, str]:
        seen["profile"] = candidate_id
        return {"candidate_id": str(candidate_id)}

    async def hints(candidate_id: object) -> list[dict[str, str]]:
        seen["hints"] = candidate_id
        return []

    monkeypatch.setattr("app.profile.service.get_candidate_features", features)
    monkeypatch.setattr("app.hints.service.recompute_candidate", hints)

    specs = [spec for spec in read_task_specs() if spec.specialization == "backend"]
    by_id = {spec.id: spec for spec in specs}
    headers = _candidate("cand-full")
    created = await db_client.post(
        "/api/v1/assessment/attempts",
        headers=headers,
        json={"specialization": "backend", "declared_grade": "middle"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    attempt_id = body["id"]
    assert body["progress"]["total"] == 12
    assert body["task"]["kind"] == "mcq"
    assert "answer" not in body["task"]
    started = datetime.fromisoformat(body["started_at"])
    deadline = datetime.fromisoformat(body["deadline_at"])
    assert deadline - started == timedelta(minutes=40)
    assert 2300 <= body["remaining_seconds"] <= 2400

    url = f"/api/v1/assessment/attempts/{attempt_id}"
    answers = f"{url}/answers"
    skipped_id = None
    answered: list[str] = []
    for _ in range(20):
        view = (await db_client.get(url, headers=headers)).json()
        task = view["task"]
        if task is None:
            break
        spec = by_id[task["id"]]
        assert "tests_hidden" not in task
        assert "answer" not in task
        if skipped_id is None:
            skipped_id = task["id"]
            saved = await db_client.post(answers, headers=headers, json={"task_id": task["id"], "skip": True})
            assert saved.status_code == 200, saved.text
            assert saved.json()["progress"]["skipped"] == 1
            assert saved.json()["task"]["id"] != skipped_id
            again = await db_client.get(url, headers=headers)
            assert again.json()["progress"] == saved.json()["progress"]
            assert again.json()["task"]["id"] == saved.json()["task"]["id"]
            continue
        if spec.kind == "mcq":
            payload: dict[str, object] = {"task_id": spec.id, "answer": spec.answer}
        else:
            payload = {"task_id": spec.id, "code": spec.solutions["python"], "language": "Python"}
            before = len(piston_exec)
            saved = await db_client.post(answers, headers=headers, json=payload)
            assert saved.status_code == 200, saved.text
            sent = [str(item["stdin"]) for item in piston_exec[before:]]
            assert sent == [case["stdin"] for case in spec.tests_hidden or ()]
            answered.append(spec.id)
            continue
        saved = await db_client.post(answers, headers=headers, json=payload)
        assert saved.status_code == 200, saved.text
        answered.append(spec.id)
    else:
        raise AssertionError("attempt never ran out of tasks")

    assert skipped_id is not None
    assert answered[-1] == skipped_id
    assert len(answered) == 12
    done = (await db_client.get(url, headers=headers)).json()
    assert done["task"] is None
    assert done["progress"]["answered"] == 12
    assert done["progress"]["skipped"] == 0

    code = by_id["backend-code-01"]
    leaked = await db_client.post(
        "/api/v1/assessment/run",
        headers=headers,
        json={"task_id": code.id, "code": code.solutions["python"], "language": "python", "hidden": True},
    )
    assert leaked.status_code == 200, leaked.text
    run_body = leaked.json()
    assert run_body["verdict"] == "OK"
    assert run_body["passed"] == len(code.tests_public or ())
    assert run_body["total"] == len(code.tests_public or ())
    for case in code.tests_hidden or ():
        assert case["stdin"].strip() not in leaked.text
        assert case["expected"].strip() not in leaked.text
    wrong = await db_client.post(
        "/api/v1/assessment/run",
        headers=headers,
        json={"task_id": code.id, "code": "print(0)\n", "language": "python"},
    )
    assert wrong.json()["verdict"] == "WRONG_ANSWER"

    other = await db_client.get(url, headers=_candidate("someone-else"))
    assert other.status_code == 404

    finished = await db_client.post(f"{url}/finish", headers=headers)
    assert finished.status_code == 200, finished.text
    result = finished.json()
    assert result["score"] == 100
    assert result["grade"] == "middle"
    assert result["ready_for_next"] is True
    assert result["rank"] == 1
    assert result["category_size"] == 1
    assert {item["skill_id"]: item["score"] for item in result["skill_scores"]} == {
        "docker": 100,
        "go": 100,
        "kafka": 100,
        "postgresql": 100,
        "python": 100,
    }

    async with session_factory() as session:
        candidate = (
            await session.execute(
                text(
                    """
                    SELECT c.id, c.grade, c.grade_score, c.specialization, c.ready_for_next,
                           c.category_rank, c.category_size
                    FROM candidates c
                    JOIN users u ON u.id = c.user_id
                    WHERE u.kc_sub = :sub
                    """
                ),
                {"sub": "cand-full"},
            )
        ).one()
        skills = (
            await session.execute(
                text(
                    """
                    SELECT cs.skill_id, cs.score, cs.source
                    FROM candidate_skills cs
                    WHERE cs.candidate_id = CAST(:id AS uuid)
                    ORDER BY cs.skill_id
                    """
                ),
                {"id": str(candidate[0])},
            )
        ).all()
    assert candidate[1:] == ("middle", 100, "backend", True, 1, 1)
    assert skills
    assert {row[2] for row in skills} == {"test"}
    assert {row[0]: row[1] for row in skills} == {item["skill_id"]: item["score"] for item in result["skill_scores"]}
    assert seen["profile"] == candidate[0]
    assert seen["hints"] == candidate[0]

    repeat = await db_client.post(f"{url}/finish", headers=headers)
    assert repeat.status_code == 409
    assert repeat.json()["error"]["code"] == "attempt_finished"


async def test_pending_code_does_not_block_finish(
    db_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PISTON_ENABLED", "false")
    get_settings.cache_clear()
    headers = _candidate("cand-pending")
    created = await db_client.post(
        "/api/v1/assessment/attempts",
        headers=headers,
        json={"specialization": "frontend", "declared_grade": "junior"},
    )
    assert created.status_code == 201, created.text
    attempt_id = created.json()["id"]
    code = next(spec for spec in read_task_specs() if spec.id == "frontend-code-01")
    saved = await db_client.post(
        f"/api/v1/assessment/attempts/{attempt_id}/answers",
        headers=headers,
        json={"task_id": code.id, "code": "print(0)\n", "language": "python"},
    )
    assert saved.status_code == 200, saved.text
    finished = await db_client.post(f"/api/v1/assessment/attempts/{attempt_id}/finish", headers=headers)
    assert finished.status_code == 200, finished.text
    assert finished.json()["score"] == 0
    async with session_factory() as session:
        verdict = await session.scalar(
            text("SELECT verdict FROM attempt_answers WHERE task_id = :task"),
            {"task": code.id},
        )
    assert verdict == "PENDING"
    get_settings.cache_clear()


async def test_deadline_blocks_answers_but_not_finish(
    db_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    headers = _candidate("cand-expired")
    created = await db_client.post(
        "/api/v1/assessment/attempts",
        headers=headers,
        json={"specialization": "devops", "declared_grade": "middle"},
    )
    assert created.status_code == 201, created.text
    attempt_id = created.json()["id"]
    async with session_factory() as session:
        await session.execute(
            text("UPDATE attempts SET deadline_at = NOW() - INTERVAL '1 minute' WHERE id = CAST(:id AS uuid)"),
            {"id": attempt_id},
        )
        await session.commit()
    denied = await db_client.post(
        f"/api/v1/assessment/attempts/{attempt_id}/answers",
        headers=headers,
        json={"task_id": "devops-mcq-01", "answer": "b"},
    )
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "attempt_expired"
    finished = await db_client.post(f"/api/v1/assessment/attempts/{attempt_id}/finish", headers=headers)
    assert finished.status_code == 200, finished.text
    assert finished.json()["score"] == 0
    assert finished.json()["grade"] == "middle"
    assert finished.json()["ready_for_next"] is False


async def test_demo_finish_sets_grade_rank_and_is_admin_only(
    client: AsyncClient,
    db_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    denied = await client.post(
        f"/api/v1/assessment/attempts/{uuid4()}/demo-finish",
        headers=_candidate("cand-no-admin"),
        json={"score": 90},
    )
    assert denied.status_code == 403

    async def open_attempt(sub: str) -> str:
        response = await db_client.post(
            "/api/v1/assessment/attempts",
            headers=_candidate(sub),
            json={"specialization": "backend", "declared_grade": "middle"},
        )
        assert response.status_code == 201, response.text
        return response.json()["id"]

    attempt_a = await open_attempt("rank-a")
    attempt_b = await open_attempt("rank-b")
    attempt_c = await open_attempt("rank-c")
    missing = await db_client.post(
        f"/api/v1/assessment/attempts/{uuid4()}/demo-finish",
        headers=_admin(),
        json={"score": 10},
    )
    assert missing.status_code == 404

    high = await db_client.post(
        f"/api/v1/assessment/attempts/{attempt_a}/demo-finish",
        headers=_admin(),
        json={"score": 80, "skill_scores": [{"skill_id": "go", "score": 80}]},
    )
    assert high.status_code == 200, high.text
    assert high.json()["grade"] == "middle"
    assert high.json()["ready_for_next"] is True
    assert high.json()["rank"] == 1
    assert high.json()["category_size"] == 1

    low = await db_client.post(
        f"/api/v1/assessment/attempts/{attempt_b}/demo-finish",
        headers=_admin(),
        json={"score": 30, "skill_scores": [{"skill_id": "kubernetes", "score": 30}]},
    )
    assert low.status_code == 200, low.text
    assert low.json()["grade"] == "middle"
    assert low.json()["ready_for_next"] is False

    mid = await db_client.post(
        f"/api/v1/assessment/attempts/{attempt_c}/demo-finish",
        headers=_admin(),
        json={"score": 60},
    )
    assert mid.status_code == 200, mid.text
    assert mid.json()["grade"] == "middle"
    assert mid.json()["ready_for_next"] is False
    assert mid.json()["rank"] == 2
    assert mid.json()["category_size"] == 3

    boundary = await open_attempt("rank-boundary")
    declared = await db_client.post(
        f"/api/v1/assessment/attempts/{boundary}/demo-finish",
        headers=_admin(),
        json={"score": 40, "grade": "senior"},
    )
    assert declared.status_code == 200, declared.text
    assert declared.json()["grade"] == "senior"
    assert declared.json()["ready_for_next"] is False

    async with session_factory() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT u.kc_sub, c.grade, c.grade_score, c.category_rank, c.category_size, c.ready_for_next
                    FROM candidates c
                    JOIN users u ON u.id = c.user_id
                    WHERE u.kc_sub IN ('rank-a', 'rank-b', 'rank-c', 'rank-boundary')
                    """
                )
            )
        ).all()
        skill_rows = (
            await session.execute(
                text(
                    """
                    SELECT u.kc_sub, cs.skill_id, cs.score, cs.source
                    FROM candidate_skills cs
                    JOIN candidates c ON c.id = cs.candidate_id
                    JOIN users u ON u.id = c.user_id
                    WHERE u.kc_sub IN ('rank-a', 'rank-b')
                    """
                )
            )
        ).all()
    found = {row[0]: row[1:] for row in rows}
    assert found["rank-a"] == ("middle", 80, 1, 3, True)
    assert found["rank-c"] == ("middle", 60, 2, 3, False)
    assert found["rank-b"] == ("middle", 30, 3, 3, False)
    assert found["rank-boundary"][0] == "senior"
    skills = {(row[0], row[1]): (row[2], row[3]) for row in skill_rows}
    assert skills[("rank-a", "go")] == (80, "test")
    assert skills[("rank-b", "kubernetes")] == (30, "test")
