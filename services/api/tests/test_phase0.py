from uuid import uuid4

import pytest
import yaml
from app.assessment import models as assessment_models  # noqa: F401
from app.chat import models as chat_models  # noqa: F401
from app.company import models as company_models  # noqa: F401
from app.core.auth import Principal, get_principal
from app.core.db import EMBEDDING_DIM, Base
from app.core.models import Job, User  # noqa: F401
from app.embeddings.service import embed
from app.invitation import models as invitation_models  # noqa: F401
from app.llm.service import extract, load_schema
from app.main import app
from app.matching.config import C_WEIGHTS, E_WEIGHTS
from app.matching.service import NeedView, build_shortlist, score_pair
from app.need import models as need_models  # noqa: F401
from app.need.schemas import NeedWrite
from app.profile import models as profile_models  # noqa: F401
from app.profile.service import get_candidate_features
from app.resume import models as resume_models  # noqa: F401
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from starlette.requests import Request


@pytest.fixture
async def client():
    async def debug_principal(request: Request) -> Principal:
        role = request.headers.get("x-debug-role", "candidate")
        sub = request.headers.get("x-debug-sub", "stub-candidate")
        email = request.headers.get("x-debug-email")
        if role not in {"candidate", "employer", "admin"}:
            role = "candidate"
        return Principal(sub=sub, role=role, email=email)

    app.dependency_overrides[get_principal] = debug_principal
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as http:
            yield http
    finally:
        app.dependency_overrides.pop(get_principal, None)


async def test_health(client: AsyncClient) -> None:
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["x-request-id"]


async def test_stub_returns_contract_error(client: AsyncClient) -> None:
    response = await client.get("/api/v1/candidates/me")
    assert response.status_code == 501
    body = response.json()
    assert set(body["error"]) >= {"code", "message"}
    assert body["error"]["code"] == "not_implemented"


async def test_wrong_role_is_forbidden(client: AsyncClient) -> None:
    response = await client.get("/api/v1/companies/me")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_need_validation_uses_error_format(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/needs",
        headers={"x-debug-role": "employer"},
        json={"title": "Backend"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_need_schema_rejects_short_description() -> None:
    payload = {
        "title": "Backend",
        "specialization": "backend",
        "grades": ["middle"],
        "salary_from": 200000,
        "salary_to": 300000,
        "formats": ["remote"],
        "must_skills": ["go"],
        "description": "коротко",
        "domain": "fintech",
        "stages": 2,
    }
    with pytest.raises(ValidationError):
        NeedWrite.model_validate(payload)


def test_tables_from_tz() -> None:
    expected = {
        "users",
        "jobs",
        "candidates",
        "candidate_skills",
        "experiences",
        "projects",
        "evidence_units",
        "fsp_achievements",
        "resumes",
        "companies",
        "needs",
        "need_requirements",
        "tasks_bank",
        "attempts",
        "attempt_answers",
        "invitations",
        "favorites",
        "messages",
    }
    assert expected <= set(Base.metadata.tables)


def test_weights_sum_to_one() -> None:
    for grade, weights in E_WEIGHTS.items():
        assert abs(sum(weights.values()) - 1) < 1e-9, grade
    for grade, weights in C_WEIGHTS.items():
        assert abs(sum(weights.values()) - 1) < 1e-9, grade


async def test_seams_are_deterministic() -> None:
    vectors = await embed(["kafka", "kafka"])
    assert len(vectors) == 2
    assert len(vectors[0]) == EMBEDDING_DIM
    assert vectors[0] == vectors[1]

    for name in ("resume", "evidence_unit", "need_requirements", "need_category"):
        schema = load_schema(name)
        assert schema["type"] == "object"
        extracted = await extract(name, "строил антифрод на Kafka")
        assert isinstance(extracted, dict)

    features = await get_candidate_features(uuid4())
    need = NeedView(
        id="n",
        specialization="backend",
        grades=["middle"],
        salary_from=200000,
        salary_to=300000,
        formats=["remote"],
        city=None,
        must_skills=["go"],
        nice_skills=[],
        domain="fintech",
        stages=2,
    )
    first = await score_pair(need, features)
    second = await score_pair(need, features)
    assert first == second
    shortlist = await build_shortlist(uuid4())
    assert shortlist.items == []


def test_contract_paths_are_registered() -> None:
    spec_path = __import__("pathlib").Path(__file__).resolve().parents[3] / "contracts" / "openapi.yaml"
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    live = app.openapi()["paths"]
    http_methods = {"get", "post", "put", "delete", "patch"}

    def methods_of(node: dict) -> set[str]:
        return {method for method in node if method in http_methods}

    assert set(spec["paths"]) == set(live)
    missing = []
    for path, node in live.items():
        file_node = spec["paths"].get(path)
        if file_node is None or methods_of(file_node) != methods_of(node):
            missing.append(path)
    assert missing == []
