"""Load committed seed JSON with SQL text(), not other modules' models.

profile.service, company.service, need.service and invitation.service are still
phase-0 stubs: none of them upserts a row. Import-linter forbids ``app.demo`` from
importing those modules' model classes, so this loader writes through
``sqlalchemy.text`` against the tables from the phase-0 migration.

Embeddings are left NULL on purpose. ``embeddings.service.embed`` returns a zero
vector, and a stored zero would poison cosine search. Agent B's ``rebuild_evidence``
is called after commit when that function exists. ``matching.service.build_shortlist``
is always called; until agent D replaces it, the stub returns an empty shortlist.

Stable UUID v5 keys make a second ``reseed`` update the same rows.
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import String, bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionLocal
from app.core.settings import get_settings

_STRINGS = ARRAY(String())
_UUIDS = ARRAY(PG_UUID(as_uuid=True))


def seed_root() -> Path:
    """Find ``seed/`` in ``SEED_DIR``, the compose mount ``/srv/seed``, or the repo."""
    env = os.environ.get("SEED_DIR")
    if env and (Path(env) / "data" / "candidates.json").is_file():
        return Path(env)
    mounted = Path("/srv/seed")
    if (mounted / "data" / "candidates.json").is_file():
        return mounted
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "seed" / "data" / "candidates.json"
        if candidate.is_file():
            return parent / "seed"
    raise FileNotFoundError("seed JSON not found; set SEED_DIR to the seed directory")


def _read(root: Path, name: str) -> Any:
    return json.loads((root / name).read_text(encoding="utf-8"))


def _uuids(values: list[str]) -> list[uuid.UUID]:
    return [uuid.UUID(value) for value in values]


def _moment(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _day(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value[:10])


def _resume_path(root: Path, stored: str) -> str:
    source = root / "demo" / "candidate.pdf"
    if not source.is_file():
        return stored
    upload = Path(get_settings().upload_dir)
    try:
        upload.mkdir(parents=True, exist_ok=True)
        dest = upload / "demo-candidate.pdf"
        shutil.copyfile(source, dest)
    except OSError:
        return str(source)
    return str(dest)


async def _run(session: AsyncSession, statement: Any, rows: list[dict[str, Any]]) -> None:
    if rows:
        await session.execute(statement, rows)


async def load_seed() -> dict[str, int]:
    root = seed_root()
    candidates = _read(root, "data/candidates.json")
    companies = _read(root, "data/companies.json")
    needs = _read(root, "data/needs.json")
    invitations = _read(root, "data/invitations.json")
    users = _read(root, "data/users.json")
    pdf_path = _resume_path(root, "seed/demo/candidate.pdf")
    async with SessionLocal() as session:
        async with session.begin():
            await _apply(session, users, candidates, companies, needs, invitations, pdf_path)
    await _after_load([row["id"] for row in candidates], [row["id"] for row in needs])
    return {
        "candidates": len(candidates),
        "companies": len(companies),
        "needs": len(needs),
        "invitations": len(invitations),
    }


async def _apply(
    session: AsyncSession,
    users: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    companies: list[dict[str, Any]],
    needs: list[dict[str, Any]],
    invitations: list[dict[str, Any]],
    pdf_path: str,
) -> None:
    candidate_ids = _uuids([row["id"] for row in candidates])
    need_ids = _uuids([row["id"] for row in needs])
    await _run(session, _USER, users)
    await _run(session, _CANDIDATE, [_candidate_row(row) for row in candidates])
    for statement in _DELETE_CANDIDATE_CHILDREN:
        await session.execute(statement, {"ids": candidate_ids})
    await _run(session, _SKILL, _skill_rows(candidates))
    await _run(session, _EXPERIENCE, _experience_rows(candidates))
    await _run(session, _PROJECT, _project_rows(candidates))
    await _run(session, _EVIDENCE, _evidence_rows(candidates))
    await _run(session, _FSP, _fsp_rows(candidates))
    await _run(session, _RESUME, _resume_rows(candidates, pdf_path))
    await _run(session, _COMPANY, [_company_row(row) for row in companies])
    await session.execute(_DELETE_INVITATIONS, {"need_ids": need_ids, "candidate_ids": candidate_ids})
    await session.execute(_DELETE_REQUIREMENTS, {"ids": need_ids})
    await _run(session, _NEED, [_need_row(row) for row in needs])
    await _run(session, _REQUIREMENT, _requirement_rows(needs))
    await _run(session, _INVITATION, [_invitation_row(row) for row in invitations])
    from app.vacancy.seed_extra import seed_demo_vacancies

    await seed_demo_vacancies(session)


async def _after_load(candidate_ids: list[str], need_ids: list[str]) -> None:
    import app.matching.service as matching
    import app.profile.service as profile_service

    rebuild = getattr(profile_service, "rebuild_evidence", None)
    if rebuild is not None:
        for candidate_id in candidate_ids:
            result = rebuild(uuid.UUID(candidate_id))
            if hasattr(result, "__await__"):
                await result
    for need_id in need_ids:
        await matching.build_shortlist(uuid.UUID(need_id))


def _candidate_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "user_id": row["user"]["id"],
        "full_name": row["full_name"],
        "city": row["city"],
        "specialization": row["specialization"],
        "grade": row["grade"],
        "grade_score": row["grade_score"],
        "ready_for_next": row["ready_for_next"],
        "category_rank": row["category_rank"],
        "category_size": row["category_size"],
        "min_salary": row["min_salary"],
        "formats": row["formats"],
        "status": row["status"],
        "visible": row["visible"],
        "liked_skills": row["liked_skills"],
        "disliked_skills": row["disliked_skills"],
        "liked_domains": row["liked_domains"],
        "blocked_domains": row["blocked_domains"],
        "last_active_at": _moment(row["last_active_at"]),
        "phone": row["phone"],
        "contact_email": row["contact_email"],
    }


def _skill_rows(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for candidate in candidates:
        for skill in candidate["skills"]:
            rows.append(
                {
                    "id": str(uuid.uuid5(uuid.UUID(candidate["id"]), f"{skill['skill_id']}:{skill['source']}")),
                    "candidate_id": candidate["id"],
                    "skill_id": skill["skill_id"],
                    "score": skill["score"],
                    "source": skill["source"],
                }
            )
    return rows


def _experience_rows(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for candidate in candidates:
        for item in candidate["experiences"]:
            rows.append(
                {
                    "id": item["id"],
                    "candidate_id": candidate["id"],
                    "company": item["company"],
                    "role": item["role"],
                    "start": _day(item["start"]),
                    "end": _day(item["end"]),
                    "description": item["description"],
                    "evidence_span": item["evidence_span"],
                }
            )
    return rows


def _project_rows(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for candidate in candidates:
        for item in candidate["projects"]:
            rows.append(
                {
                    "id": item["id"],
                    "candidate_id": candidate["id"],
                    "task": item["task"],
                    "role": item["role"],
                    "skills": item["skills"],
                    "scale": item["scale"],
                    "outcome": item["outcome"],
                    "occurred_on": _day(item["date"]),
                    "url": item["url"],
                    "source": item["source"],
                }
            )
    return rows


def _evidence_rows(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for candidate in candidates:
        for item in candidate["evidence"]:
            rows.append(
                {
                    "id": item["id"],
                    "candidate_id": candidate["id"],
                    "origin": item["origin"],
                    "origin_id": item["origin_id"],
                    "task": item["task"],
                    "domain": item["domain"],
                    "skills": item["skills"],
                    "role": item["role"],
                    "occurred_on": _day(item["date"]),
                    "trust": item["trust"],
                    "evidence_span": item["evidence_span"],
                }
            )
    return rows


def _fsp_rows(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for candidate in candidates:
        for item in candidate["fsp"]:
            rows.append(
                {
                    "id": item["id"],
                    "candidate_id": candidate["id"],
                    "discipline": item["discipline"],
                    "event": item["event"],
                    "place": item["place"],
                    "year": item["year"],
                }
            )
    return rows


def _resume_rows(candidates: list[dict[str, Any]], pdf_path: str) -> list[dict[str, Any]]:
    rows = []
    for candidate in candidates:
        resume = candidate.get("resume")
        if not resume:
            continue
        rows.append(
            {
                "id": resume["id"],
                "candidate_id": candidate["id"],
                "file_path": pdf_path,
                "status": resume["status"],
                "raw_text": resume["raw_text"],
                "parsed_json": resume["parsed_json"],
                "error": None,
            }
        )
    return rows


def _company_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "owner_user_id": row["user"]["id"],
        "name": row["name"],
        "city": row["city"],
        "size": row["size"],
        "industry": row["industry"],
        "about": row["about"],
        "recruiter_contact": row["recruiter_contact"],
        "benefits": row["benefits"],
    }


def _need_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "company_id": row["company_id"],
        "title": row["title"],
        "specialization": row["specialization"],
        "grades": row["grades"],
        "salary_from": row["salary_from"],
        "salary_to": row["salary_to"],
        "formats": row["formats"],
        "city": row["city"],
        "must_skills": row["must_skills"],
        "nice_skills": row["nice_skills"],
        "description": row["description"],
        "domain": row["domain"],
        "stages": row["stages"],
        "status": row["status"],
    }


def _invitation_row(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    for key in ("deadline", "created_at", "viewed_at", "accepted_at", "declined_at", "expired_at", "revoked_at"):
        payload[key] = _moment(row.get(key))
    return payload


def _requirement_rows(needs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for need in needs:
        for item in need["requirements"]:
            rows.append(
                {
                    "id": item["id"],
                    "need_id": need["id"],
                    "task": item["task"],
                    "domain": item["domain"],
                    "skills": item["skills"],
                    "scale": item["scale"],
                    "kind": item["kind"],
                    "evidence_span": item["evidence_span"],
                }
            )
    return rows


_USER = text(
    """
    INSERT INTO users (id, kc_sub, role, email)
    VALUES (CAST(:id AS uuid), :kc_sub, :role, :email)
    ON CONFLICT (id) DO UPDATE SET
        kc_sub = EXCLUDED.kc_sub,
        role = EXCLUDED.role,
        email = EXCLUDED.email
    """
)

_CANDIDATE = text(
    """
    INSERT INTO candidates (
        id, user_id, full_name, city, specialization, grade, grade_score,
        ready_for_next, category_rank, category_size, min_salary, formats,
        status, visible, liked_skills, disliked_skills, liked_domains,
        blocked_domains, last_active_at, phone, contact_email
    ) VALUES (
        CAST(:id AS uuid), CAST(:user_id AS uuid), :full_name, :city, :specialization, :grade, :grade_score,
        :ready_for_next, :category_rank, :category_size, :min_salary, :formats,
        :status, :visible, :liked_skills, :disliked_skills, :liked_domains,
        :blocked_domains, CAST(:last_active_at AS timestamptz), :phone, :contact_email
    )
    ON CONFLICT (id) DO UPDATE SET
        user_id = EXCLUDED.user_id,
        full_name = EXCLUDED.full_name,
        city = EXCLUDED.city,
        specialization = EXCLUDED.specialization,
        grade = EXCLUDED.grade,
        grade_score = EXCLUDED.grade_score,
        ready_for_next = EXCLUDED.ready_for_next,
        category_rank = EXCLUDED.category_rank,
        category_size = EXCLUDED.category_size,
        min_salary = EXCLUDED.min_salary,
        formats = EXCLUDED.formats,
        status = EXCLUDED.status,
        visible = EXCLUDED.visible,
        liked_skills = EXCLUDED.liked_skills,
        disliked_skills = EXCLUDED.disliked_skills,
        liked_domains = EXCLUDED.liked_domains,
        blocked_domains = EXCLUDED.blocked_domains,
        last_active_at = EXCLUDED.last_active_at,
        phone = EXCLUDED.phone,
        contact_email = EXCLUDED.contact_email
    """
).bindparams(
    bindparam("formats", type_=_STRINGS),
    bindparam("liked_skills", type_=_STRINGS),
    bindparam("disliked_skills", type_=_STRINGS),
    bindparam("liked_domains", type_=_STRINGS),
    bindparam("blocked_domains", type_=_STRINGS),
)

_DELETE_CANDIDATE_CHILDREN = tuple(
    text(f"DELETE FROM {table} WHERE candidate_id = ANY(:ids)").bindparams(bindparam("ids", type_=_UUIDS))
    for table in ("candidate_skills", "experiences", "projects", "evidence_units", "fsp_achievements", "resumes")
)

_SKILL = text(
    """
    INSERT INTO candidate_skills (id, candidate_id, skill_id, score, source)
    VALUES (CAST(:id AS uuid), CAST(:candidate_id AS uuid), :skill_id, :score, :source)
    """
)

_EXPERIENCE = text(
    """
    INSERT INTO experiences (id, candidate_id, company, role, start, "end", description, evidence_span)
    VALUES (
        CAST(:id AS uuid), CAST(:candidate_id AS uuid), :company, :role,
        CAST(:start AS date), CAST(:end AS date), :description, :evidence_span
    )
    """
)

_PROJECT = text(
    """
    INSERT INTO projects (id, candidate_id, task, role, skills, scale, outcome, date, url, source)
    VALUES (
        CAST(:id AS uuid), CAST(:candidate_id AS uuid), :task, :role, :skills, :scale, :outcome,
        CAST(:occurred_on AS date), :url, :source
    )
    """
).bindparams(bindparam("skills", type_=_STRINGS))

_EVIDENCE = text(
    """
    INSERT INTO evidence_units (
        id, candidate_id, origin, origin_id, task, domain, skills, role, date, trust, evidence_span
    ) VALUES (
        CAST(:id AS uuid), CAST(:candidate_id AS uuid), :origin, CAST(:origin_id AS uuid), :task, :domain,
        :skills, :role, CAST(:occurred_on AS date), :trust, :evidence_span
    )
    """
).bindparams(bindparam("skills", type_=_STRINGS))

_FSP = text(
    """
    INSERT INTO fsp_achievements (id, candidate_id, discipline, event, place, year)
    VALUES (CAST(:id AS uuid), CAST(:candidate_id AS uuid), :discipline, :event, :place, :year)
    """
)

_RESUME = text(
    """
    INSERT INTO resumes (id, candidate_id, file_path, status, raw_text, parsed_json, error)
    VALUES (
        CAST(:id AS uuid), CAST(:candidate_id AS uuid), :file_path, :status, :raw_text, :parsed_json, :error
    )
    """
).bindparams(bindparam("parsed_json", type_=JSONB))

_COMPANY = text(
    """
    INSERT INTO companies (
        id, owner_user_id, name, city, size, industry, about, recruiter_contact, benefits
    ) VALUES (
        CAST(:id AS uuid), CAST(:owner_user_id AS uuid), :name, :city, :size, :industry, :about,
        :recruiter_contact, :benefits
    )
    ON CONFLICT (id) DO UPDATE SET
        owner_user_id = EXCLUDED.owner_user_id,
        name = EXCLUDED.name,
        city = EXCLUDED.city,
        size = EXCLUDED.size,
        industry = EXCLUDED.industry,
        about = EXCLUDED.about,
        recruiter_contact = EXCLUDED.recruiter_contact,
        benefits = EXCLUDED.benefits
    """
).bindparams(bindparam("recruiter_contact", type_=JSONB), bindparam("benefits", type_=_STRINGS))

_DELETE_INVITATIONS = text(
    """
    DELETE FROM invitations
    WHERE need_id = ANY(:need_ids) OR candidate_id = ANY(:candidate_ids)
    """
).bindparams(bindparam("need_ids", type_=_UUIDS), bindparam("candidate_ids", type_=_UUIDS))

_DELETE_REQUIREMENTS = text("DELETE FROM need_requirements WHERE need_id = ANY(:ids)").bindparams(
    bindparam("ids", type_=_UUIDS)
)

_NEED = text(
    """
    INSERT INTO needs (
        id, company_id, title, specialization, grades, salary_from, salary_to, formats,
        city, must_skills, nice_skills, description, domain, stages, status
    ) VALUES (
        CAST(:id AS uuid), CAST(:company_id AS uuid), :title, :specialization, :grades, :salary_from,
        :salary_to, :formats, :city, :must_skills, :nice_skills, :description, :domain, :stages, :status
    )
    ON CONFLICT (id) DO UPDATE SET
        company_id = EXCLUDED.company_id,
        title = EXCLUDED.title,
        specialization = EXCLUDED.specialization,
        grades = EXCLUDED.grades,
        salary_from = EXCLUDED.salary_from,
        salary_to = EXCLUDED.salary_to,
        formats = EXCLUDED.formats,
        city = EXCLUDED.city,
        must_skills = EXCLUDED.must_skills,
        nice_skills = EXCLUDED.nice_skills,
        description = EXCLUDED.description,
        domain = EXCLUDED.domain,
        stages = EXCLUDED.stages,
        status = EXCLUDED.status
    """
).bindparams(
    bindparam("grades", type_=_STRINGS),
    bindparam("formats", type_=_STRINGS),
    bindparam("must_skills", type_=_STRINGS),
    bindparam("nice_skills", type_=_STRINGS),
)

_REQUIREMENT = text(
    """
    INSERT INTO need_requirements (id, need_id, task, domain, skills, scale, kind, evidence_span)
    VALUES (
        CAST(:id AS uuid), CAST(:need_id AS uuid), :task, :domain, :skills, :scale, :kind, :evidence_span
    )
    """
).bindparams(bindparam("skills", type_=_STRINGS))

_INVITATION = text(
    """
    INSERT INTO invitations (
        id, need_id, candidate_id, status, title, message, salary_from, salary_to,
        contact_channel, contact_value, deadline, decline_reason, hiring_stage,
        created_at, viewed_at, accepted_at, declined_at, expired_at, revoked_at
    ) VALUES (
        CAST(:id AS uuid), CAST(:need_id AS uuid), CAST(:candidate_id AS uuid), :status, :title, :message,
        :salary_from, :salary_to, :contact_channel, :contact_value, CAST(:deadline AS timestamptz),
        :decline_reason, :hiring_stage, CAST(:created_at AS timestamptz), CAST(:viewed_at AS timestamptz),
        CAST(:accepted_at AS timestamptz), CAST(:declined_at AS timestamptz), CAST(:expired_at AS timestamptz),
        CAST(:revoked_at AS timestamptz)
    )
    """
)
