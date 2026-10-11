import io

import fitz
import pytest
from app.core import db
from app.core.db import EMBEDDING_DIM
from app.core.settings import get_settings
from app.llm.service import sanitize
from app.main import app
from app.profile.models import Experience
from app.profile.service import get_candidate_features
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from tests.test_profile import headers, prepare_database, truncate_database

PHRASE = "Romashka backend Kafka antifraud"


def make_pdf(text: str, pages: int = 1) -> bytes:
    document = fitz.open()
    for index in range(pages):
        page = document.new_page()
        if index == 0 and text:
            page.insert_text((72, 72), text)
    buffer = io.BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()


def pdf_plain_text(data: bytes) -> str:
    with fitz.open(stream=data, filetype="pdf") as document:
        return sanitize("\n".join(page.get_text() for page in document))


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
def uploads(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    get_settings.cache_clear()
    yield tmp_path


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


@pytest.fixture
def fake_embed(monkeypatch: pytest.MonkeyPatch):
    async def _embed(texts: list[str], prefix: str = "passage") -> list[list[float]]:
        return [[0.5] * EMBEDDING_DIM for _ in texts]

    monkeypatch.setattr("app.embeddings.service.embed", _embed)


@pytest.fixture
def hints(monkeypatch: pytest.MonkeyPatch):
    calls: list = []

    async def _recompute(candidate_id):
        calls.append(candidate_id)
        return []

    monkeypatch.setattr("app.hints.service.recompute_candidate", _recompute)
    return calls


async def test_resume_rejects_size_pages_and_type(database, client: AsyncClient, uploads) -> None:
    too_big = await client.post(
        "/api/v1/candidates/me/resume",
        headers=headers("resume-limits"),
        files={"file": ("cv.pdf", b"x" * (5 * 1024 * 1024 + 1), "application/pdf")},
    )
    assert too_big.status_code == 400
    assert too_big.json()["error"]["code"] == "resume_too_large"

    many_pages = await client.post(
        "/api/v1/candidates/me/resume",
        headers=headers("resume-limits"),
        files={"file": ("cv.pdf", make_pdf("", pages=6), "application/pdf")},
    )
    assert many_pages.status_code == 400
    assert many_pages.json()["error"]["code"] == "resume_too_many_pages"

    not_pdf = await client.post(
        "/api/v1/candidates/me/resume",
        headers=headers("resume-limits"),
        files={"file": ("cv.txt", b"hello", "text/plain")},
    )
    assert not_pdf.status_code == 400
    assert not_pdf.json()["error"]["code"] == "resume_invalid"


async def test_resume_confirm_keeps_quoted_fields_and_builds_evidence(
    database, client: AsyncClient, uploads, fake_embed, hints
) -> None:
    data = make_pdf(PHRASE)
    source = pdf_plain_text(data)
    assert PHRASE in source
    uploaded = await client.post(
        "/api/v1/candidates/me/resume",
        headers=headers("resume-ok"),
        files={"file": ("cv.pdf", data, "application/pdf")},
    )
    assert uploaded.status_code == 201
    body = uploaded.json()
    assert body["status"] == "parsed"
    resume_id = body["resume_id"]

    viewed = await client.get(f"/api/v1/candidates/me/resume/{resume_id}", headers=headers("resume-ok"))
    assert viewed.status_code == 200
    assert viewed.json()["status"] == "parsed"
    assert viewed.json()["parsed"]["experiences"] == []

    confirmed = await client.post(
        f"/api/v1/candidates/me/resume/{resume_id}/confirm",
        headers=headers("resume-ok"),
        json={
            "experiences": [
                {
                    "company": "Romashka",
                    "role": "Backend",
                    "start": "2022-01-01T00:00:00Z",
                    "end": None,
                    "description": "antifraud",
                    "evidence_span": PHRASE,
                },
                {
                    "company": "Invented",
                    "role": "CEO",
                    "description": "nope",
                    "evidence_span": "this quote is absent",
                },
            ],
            "skills": [
                {"name": "Kafka", "evidence_span": "Kafka"},
                {"name": "NotASkill", "evidence_span": "Kafka"},
                {"name": "Haskell", "evidence_span": "this quote is absent"},
            ],
            "projects": [
                {
                    "task": "antifraud service",
                    "role": "owner",
                    "skills": ["kafka", "python"],
                    "outcome": "shipped",
                    "evidence_span": "Kafka antifraud",
                }
            ],
        },
    )
    assert confirmed.status_code == 200
    parsed = confirmed.json()["parsed"]
    assert confirmed.json()["status"] == "confirmed"
    assert len(parsed["experiences"]) == 1
    assert parsed["experiences"][0]["company"] == "Romashka"
    assert [item["skill_id"] for item in parsed["skills"]] == ["kafka"]
    assert len(parsed["projects"]) == 1

    profile = await client.get("/api/v1/candidates/me", headers=headers("resume-ok"))
    profile_body = profile.json()
    assert len(profile_body["experiences"]) == 1
    assert profile_body["experiences"][0]["evidence_span"] == PHRASE
    assert {(item["skill_id"], item["source"]) for item in profile_body["skills"]} == {("kafka", "resume")}
    assert profile_body["projects"][0]["source"] == "resume"
    assert profile_body["projects"][0]["skills"] == ["kafka", "python"]

    features = await get_candidate_features(profile_body["id"])
    origins = {item.origin: item.trust for item in features.evidence}
    assert origins["experience"] == 0.6
    assert origins["project"] == 0.6
    assert all(item.embedding is not None and len(item.embedding) == EMBEDDING_DIM for item in features.evidence)
    assert hints

    async with db.SessionLocal() as session:
        rows = list(await session.scalars(select(Experience)))
        companies = [row.company for row in rows]
    assert companies == ["Romashka"]


async def test_confirm_before_parse_is_rejected(database, client: AsyncClient, uploads) -> None:
    uploaded = await client.post(
        "/api/v1/candidates/me/resume",
        headers=headers("resume-early"),
        files={"file": ("cv.pdf", make_pdf(PHRASE), "application/pdf")},
    )
    resume_id = uploaded.json()["resume_id"]
    async with db.SessionLocal() as session:
        from app.resume.models import Resume

        resume = await session.get(Resume, resume_id)
        assert resume is not None
        resume.status = "parsing"
        await session.commit()
    response = await client.post(
        f"/api/v1/candidates/me/resume/{resume_id}/confirm",
        headers=headers("resume-early"),
        json={"experiences": [], "skills": [], "projects": []},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "resume_not_ready"
