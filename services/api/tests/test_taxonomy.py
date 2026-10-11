import pytest
from app.embeddings.service import reset_model
from app.main import app
from app.taxonomy.service import (
    catalog,
    decay_of,
    list_decline_reasons,
    list_domains,
    list_specializations,
    normalize,
    search_skills,
)
from httpx import ASGITransport, AsyncClient


@pytest.fixture(autouse=True)
def _reset_embedding_cache():
    import app.taxonomy.service as taxonomy

    reset_model()
    taxonomy._EMBED_CACHE = None
    yield
    reset_model()
    taxonomy._EMBED_CACHE = None


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


def test_catalog_shape() -> None:
    data = catalog()
    assert 140 <= len(data.skills) <= 170
    assert len({skill.id for skill in data.skills}) == len(data.skills)
    assert {skill.decay for skill in data.skills} <= {"fundamental", "framework"}
    assert all(skill.specializations for skill in data.skills)
    specs = list_specializations()
    assert len(specs) == 4
    assert all(item.adjacent for item in specs)
    assert {item.id for item in specs} == {"backend", "frontend", "data_ml", "devops"}
    assert len(list_domains()) == 10
    assert len(list_decline_reasons()) >= 5
    assert decay_of("kafka") == "framework"
    assert decay_of("algorithms") == "fundamental"


def test_normalize_synonyms_case_and_typos() -> None:
    assert normalize("PYTHON") == "python"
    assert normalize("постгрес") == "postgresql"
    assert normalize("K8S") == "kubernetes"
    assert normalize("pyton") == "python"
    assert normalize("kubernets") == "kubernetes"
    assert normalize("javascrpt") == "javascript"
    assert normalize("qwertyuiopasdf") is None
    assert normalize("   ") is None


def test_search_ranks_prefix_and_limits() -> None:
    hits = search_skills("пи", limit=10)
    assert any(hit.id == "python" for hit in hits)
    react = search_skills("react", limit=5)
    assert react[0].id == "react"
    assert len(search_skills("", limit=3)) == 3
    assert len(search_skills("sql", limit=100)) <= 50


async def test_taxonomy_endpoints(client: AsyncClient) -> None:
    skills = await client.get("/api/v1/taxonomy/skills", params={"q": "каф", "limit": 5})
    assert skills.status_code == 200
    assert any(item["id"] == "kafka" for item in skills.json())
    specs = await client.get("/api/v1/taxonomy/specializations")
    domains = await client.get("/api/v1/taxonomy/domains")
    reasons = await client.get("/api/v1/taxonomy/decline-reasons")
    assert specs.status_code == domains.status_code == reasons.status_code == 200
    assert len(specs.json()) == 4
    assert len(domains.json()) == 10
    assert {item["id"] for item in reasons.json()} >= {"salary", "stack", "format", "found_job", "other"}


def test_embedding_fallback_when_model_is_already_loaded() -> None:
    import app.embeddings.service as embeddings
    import app.taxonomy.service as taxonomy

    class FakeModel:
        def encode(self, texts, batch_size=32, normalize_embeddings=True):
            rows = []
            for text in texts:
                if str(text).startswith("query:") or "kafka" in str(text).lower():
                    rows.append([1.0, 0.0])
                else:
                    rows.append([0.0, 1.0])
            return rows

    embeddings._model = FakeModel()
    embeddings._missing = False
    taxonomy._EMBED_CACHE = None
    assert normalize("qwertyuiopasdf") == "kafka"
