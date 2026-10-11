"""Need validation stays strict. Parse falls back to form skills when the LLM is off."""

from uuid import uuid4

import pytest
from app.core.auth import Principal
from app.core.db import SessionLocal
from app.core.enums import Specialization
from app.core.models import User
from app.core.settings import get_settings
from app.need.models import NeedRequirement
from app.need.schemas import NeedWrite
from app.need.service import plan_parse, requirements_from_form, resolve_contacts
from app.profile.models import Candidate, CandidateSkill
from pydantic import ValidationError
from sqlalchemy import delete, select, text


def _body(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "title": "Backend",
        "specialization": "backend",
        "grades": ["middle"],
        "salary_from": 200_000,
        "salary_to": 400_000,
        "formats": ["remote"],
        "must_skills": ["go"],
        "nice_skills": ["kafka"],
        "description": "Команда собирает платёжный контур. " * 20,
        "domain": "fintech",
        "stages": 2,
    }
    payload.update(overrides)
    return payload


def test_need_write_keeps_need_1_bounds() -> None:
    NeedWrite.model_validate(_body())
    with pytest.raises(ValidationError):
        NeedWrite.model_validate(_body(description="коротко"))
    with pytest.raises(ValidationError):
        NeedWrite.model_validate(_body(salary_to=100_000))
    with pytest.raises(ValidationError):
        NeedWrite.model_validate(_body(must_skills=["a", "b", "c", "d", "e", "f"]))
    with pytest.raises(ValidationError):
        NeedWrite.model_validate(_body(grades=["intern", "lead"]))
    with pytest.raises(ValidationError):
        NeedWrite.model_validate(_body(must_skills=["go"], nice_skills=["go"]))
    NeedWrite.model_validate(_body(grades=["middle", "senior"]))


def test_form_requirements_skip_experience_fit_inputs() -> None:
    rows = requirements_from_form(["go"], ["kafka"], "fintech")
    assert [row["kind"] for row in rows] == ["must", "nice"]
    assert rows[0]["skills"] == ["go"]
    assert rows[0]["evidence_span"] is None
    assert all(row["scale"] is None for row in rows)


async def test_disabled_llm_does_not_call_extract_or_embed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "llm_enabled", False)

    async def explode(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise AssertionError("external call")

    monkeypatch.setattr("app.need.service.extract", explode)
    monkeypatch.setattr("app.need.service.embed", explode)
    plan = await plan_parse("описание " * 40, ["go"], ["kafka"], "fintech")
    assert plan.llm_used is False
    assert plan.category is None
    assert plan.embeddings is None
    assert [row["kind"] for row in plan.requirements] == ["must", "nice"]


async def test_enabled_llm_embeds_requirements_and_drops_spans(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "llm_enabled", True)
    description = "Нужен поток событий на kafka в финтехе. " * 12

    async def fake_extract(schema_name: str, text: str) -> dict[str, object]:
        assert text == description
        if schema_name == "need_requirements":
            return {
                "requirements": [
                    {
                        "task": "поток событий",
                        "domain": "fintech",
                        "skills": ["kafka"],
                        "scale": "10k rps",
                        "kind": "must",
                        "evidence_span": "поток событий",
                    },
                    {
                        "task": "чужая цитата",
                        "domain": None,
                        "skills": ["go"],
                        "scale": None,
                        "kind": "nice",
                        "evidence_span": "этой фразы нет в тексте",
                    },
                ]
            }
        return {
            "specialization": "backend",
            "grades": ["middle", "senior"],
            "domain": "fintech",
            "evidence_span": "финтехе",
        }

    async def fake_embed(texts: list[str]) -> list[list[float]]:
        assert len(texts) == 1
        assert "поток событий" in texts[0]
        assert "kafka" in texts[0]
        return [[0.0, 0.2, 0.0]]

    monkeypatch.setattr("app.need.service.extract", fake_extract)
    monkeypatch.setattr("app.need.service.embed", fake_embed)
    plan = await plan_parse(description, ["go"], [], "fintech")
    assert plan.llm_used is True
    assert len(plan.requirements) == 1
    assert plan.requirements[0]["task"] == "поток событий"
    assert plan.embeddings == [[0.0, 0.2, 0.0]]
    assert plan.category is not None
    assert plan.category.specialization == Specialization.backend
    assert plan.category.grades == ["middle", "senior"]


async def test_contacts_stay_hidden_until_invitation_service_says_otherwise() -> None:
    revealed, email, phone = await resolve_contacts(uuid4(), uuid4())
    assert revealed is False
    assert email is None
    assert phone is None


async def _postgres_ready() -> bool:
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1 FROM needs LIMIT 1"))
            await session.rollback()
    except Exception:
        return False
    return True


async def test_persist_parse_and_match_job_against_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    if not await _postgres_ready():
        pytest.skip("postgres unavailable")
    monkeypatch.setattr(get_settings(), "llm_enabled", False)
    employer = Principal(sub=f"employer-{uuid4()}", role="employer")
    user_ids: list[object] = []
    candidate_ids: list[object] = []
    need_id = None
    company_id = None
    job_id = None
    try:
        async with SessionLocal() as session:
            from app.need.service import create_need, execute_match, open_match_job, parse_need

            created = await create_need(session, employer, NeedWrite.model_validate(_body()))
            need_id = created.id
            company_id = created.company_id
            for name, status, score in (
                ("good", "seeking", 90.0),
                ("gated", "seeking", 10.0),
                ("paused", "paused", 90.0),
            ):
                user = User(kc_sub=f"{name}-{uuid4()}", role="candidate")
                session.add(user)
                await session.flush()
                user_ids.append(user.id)
                candidate = Candidate(
                    user_id=user.id,
                    full_name=f"{name} Кандидат",
                    specialization="backend",
                    grade="middle",
                    min_salary=100_000,
                    formats=["remote"],
                    status=status,
                    visible=True,
                    liked_skills=["go"],
                    liked_domains=["fintech"],
                )
                session.add(candidate)
                await session.flush()
                candidate_ids.append(candidate.id)
                session.add(CandidateSkill(candidate_id=candidate.id, skill_id="go", score=score, source="test"))
            await session.commit()
            good_id, gated_id, paused_id = candidate_ids

        async with SessionLocal() as session:
            from app.matching.service import build_shortlist_strict

            shortlist = await build_shortlist_strict(need_id)
            main_ids = {item.candidate_id for item in shortlist.items}
            hidden_ids = {item.candidate_id for item in shortlist.hidden}
            assert str(good_id) in main_ids
            assert str(gated_id) in hidden_ids
            assert str(paused_id) not in main_ids
            assert str(paused_id) not in hidden_ids
            good = next(item for item in shortlist.items if item.candidate_id == str(good_id))
            assert good.position >= 1
            assert good.breakdown.explanations
            assert not hasattr(good, "email")

        async with SessionLocal() as session:
            from app.need.service import parse_need

            parsed = await parse_need(session, employer, need_id)
            await session.commit()
            assert parsed.llm_used is False
            assert [item.kind.value for item in parsed.requirements] == ["must", "nice"]
            stored = await session.scalar(select(NeedRequirement).where(NeedRequirement.need_id == need_id))
            assert stored is not None
            assert stored.embedding is None

        async with SessionLocal() as session:
            from app.need.service import execute_match, open_match_job

            job_id = await open_match_job(session, employer, need_id)
            await session.commit()
        await execute_match(str(need_id), str(job_id))
        async with SessionLocal() as session:
            from app.core.jobs import get_job

            job = await get_job(session, job_id)
            assert job is not None
            assert job.status == "done"
            assert job.result["count"] >= 1
    finally:
        async with SessionLocal() as session:
            if need_id is not None:
                await session.execute(delete(NeedRequirement).where(NeedRequirement.need_id == need_id))
                from app.need.models import Need

                await session.execute(delete(Need).where(Need.id == need_id))
            if candidate_ids:
                await session.execute(delete(CandidateSkill).where(CandidateSkill.candidate_id.in_(candidate_ids)))
                await session.execute(delete(Candidate).where(Candidate.id.in_(candidate_ids)))
            if company_id is not None:
                await session.execute(text("DELETE FROM companies WHERE id = :id"), {"id": company_id})
            if user_ids:
                await session.execute(delete(User).where(User.id.in_(user_ids)))
            employer_user = await session.scalar(select(User).where(User.kc_sub == employer.sub))
            if employer_user is not None:
                await session.execute(delete(User).where(User.id == employer_user.id))
            if job_id is not None:
                from app.core.models import Job

                await session.execute(delete(Job).where(Job.id == job_id))
            await session.commit()
