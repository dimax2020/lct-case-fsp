"""ORM-backed profile operations. Imported by the profile router, not by other modules."""

import json
import logging
import sys
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import db
from app.core.auth import Principal
from app.core.enums import Grade, SkillSource, Specialization
from app.core.errors import AppError
from app.core.models import User
from app.core.provision import provision_user, set_candidate_hook
from app.profile.fsp import load_achievements
from app.profile.models import Candidate, CandidateSkill, EvidenceUnit, Experience, FspAchievement, Project
from app.profile.parsing import as_date, canonical_role, display_name, experience_years
from app.profile.present import candidate_profile, project_out
from app.profile.schemas import (
    CandidateProfile,
    CandidateSettings,
    CandidateUpdate,
    GradeHistoryItem,
    GradeView,
    HiddenCompany,
    Me,
    ProjectIn,
    ProjectOut,
    SkillScore,
)
from app.profile.service import CandidateFeatures, EvidenceFeature, FspFeature, SkillFeature, bind
from app.taxonomy.service import normalize, normalize_domain

logger = logging.getLogger(__name__)

def _empty_features(candidate_id: UUID) -> CandidateFeatures:
    return CandidateFeatures(
        candidate_id=str(candidate_id),
        full_name="",
        display_name="",
        specialization=None,
        grade=None,
        grade_score=None,
        min_salary=None,
        formats=[],
        status="paused",
        visible=False,
        city=None,
        liked_skills=[],
        disliked_skills=[],
        liked_domains=[],
        blocked_domains=[],
        last_active_at=None,
    )


def _vector(value: Any) -> list[float] | None:
    if value is None:
        return None
    return [float(item) for item in list(value)]


async def get_candidate_features(candidate_id: UUID) -> CandidateFeatures:
    """Read matching features from the database. A missing row is an empty profile."""
    async with db.SessionLocal() as session:
        candidate = await session.get(Candidate, candidate_id)
        if candidate is None:
            return _empty_features(candidate_id)
        skills = list(
            await session.scalars(select(CandidateSkill).where(CandidateSkill.candidate_id == candidate_id))
        )
        units = list(await session.scalars(select(EvidenceUnit).where(EvidenceUnit.candidate_id == candidate_id)))
        achievements = list(
            await session.scalars(select(FspAchievement).where(FspAchievement.candidate_id == candidate_id))
        )
        experiences = list(await session.scalars(select(Experience).where(Experience.candidate_id == candidate_id)))
        invites = await _open_invites(session, candidate_id)
        return CandidateFeatures(
            candidate_id=str(candidate.id),
            full_name=candidate.full_name or "",
            display_name=display_name(candidate.full_name or ""),
            specialization=candidate.specialization,
            grade=candidate.grade,
            grade_score=candidate.grade_score,
            min_salary=candidate.min_salary,
            formats=list(candidate.formats or []),
            status=candidate.status,
            visible=bool(candidate.visible),
            city=candidate.city,
            liked_skills=list(candidate.liked_skills or []),
            disliked_skills=list(candidate.disliked_skills or []),
            liked_domains=list(candidate.liked_domains or []),
            blocked_domains=list(candidate.blocked_domains or []),
            last_active_at=candidate.last_active_at,
            skills=[SkillFeature(skill_id=row.skill_id, score=row.score, source=row.source) for row in skills],
            evidence=[
                EvidenceFeature(
                    id=str(row.id),
                    task=row.task,
                    domain=row.domain,
                    skills=list(row.skills or []),
                    role=row.role,
                    date=row.occurred_on,
                    trust=row.trust,
                    embedding=_vector(row.embedding),
                    origin=row.origin,
                    evidence_span=row.evidence_span,
                )
                for row in units
            ],
            fsp=[
                FspFeature(discipline=row.discipline, event=row.event, place=row.place, year=row.year)
                for row in achievements
            ],
            open_invites=invites,
            experience_years=experience_years(experiences),
        )


async def get_or_create_candidate(session: AsyncSession, user_id: UUID) -> Candidate:
    found = await session.scalar(select(Candidate).where(Candidate.user_id == user_id))
    if found is not None:
        return found
    candidate = Candidate(user_id=user_id, full_name="", status="paused", visible=True)
    session.add(candidate)
    await session.flush()
    return candidate


async def ensure_candidate(user_id: UUID) -> UUID:
    """Create the candidate row for a user and return its id."""
    async with db.SessionLocal() as session:
        candidate = await get_or_create_candidate(session, user_id)
        await session.commit()
        return candidate.id


async def _candidate_hook(session: AsyncSession, user: User) -> None:
    await get_or_create_candidate(session, user.id)


async def current_candidate(session: AsyncSession, principal: Principal) -> Candidate:
    user = await provision_user(session, principal)
    return await get_or_create_candidate(session, user.id)


def require_skills(values: list[str]) -> list[str]:
    found: list[str] = []
    for raw in values:
        skill_id = normalize(raw)
        if skill_id is None:
            raise AppError("unknown_skill", f"Неизвестный навык: {raw}", status_code=400)
        if skill_id not in found:
            found.append(skill_id)
    return found


def require_domains(values: list[str]) -> list[str]:
    found: list[str] = []
    for raw in values:
        domain_id = normalize_domain(raw)
        if domain_id is None:
            raise AppError("unknown_domain", f"Неизвестный домен: {raw}", status_code=400)
        if domain_id not in found:
            found.append(domain_id)
    return found


async def _touch(candidate: Candidate) -> None:
    candidate.last_active_at = datetime.now(UTC)


async def _load_skills(session: AsyncSession, candidate_id: UUID) -> list[CandidateSkill]:
    rows = await session.scalars(
        select(CandidateSkill)
        .where(CandidateSkill.candidate_id == candidate_id)
        .order_by(CandidateSkill.skill_id, CandidateSkill.source)
    )
    return list(rows)


async def _load_projects(session: AsyncSession, candidate_id: UUID) -> list[Project]:
    rows = await session.scalars(
        select(Project)
        .where(Project.candidate_id == candidate_id)
        .order_by(Project.occurred_on.desc().nulls_last(), Project.created_at.desc())
    )
    return list(rows)


async def _load_experiences(session: AsyncSession, candidate_id: UUID) -> list[Experience]:
    rows = await session.scalars(
        select(Experience).where(Experience.candidate_id == candidate_id).order_by(Experience.start.desc().nulls_last())
    )
    return list(rows)


async def _load_achievements(session: AsyncSession, candidate_id: UUID) -> list[FspAchievement]:
    rows = await session.scalars(
        select(FspAchievement)
        .where(FspAchievement.candidate_id == candidate_id)
        .order_by(FspAchievement.year.desc().nulls_last())
    )
    return list(rows)


async def profile_view(session: AsyncSession, candidate: Candidate) -> CandidateProfile:
    await _touch(candidate)
    return candidate_profile(
        candidate,
        await _load_skills(session, candidate.id),
        await _load_projects(session, candidate.id),
        await _load_experiences(session, candidate.id),
        await _load_achievements(session, candidate.id),
    )


def clean_soft_skills(values: list[str] | None) -> list[str]:
    found: list[str] = []
    for raw in values or []:
        text = str(raw).strip()
        if text and text not in found:
            found.append(text)
    return found


def apply_profile_update(candidate: Candidate, data: dict[str, Any]) -> None:
    if "full_name" in data:
        candidate.full_name = data["full_name"] or ""
    if "city" in data:
        candidate.city = data["city"]
    if "specialization" in data:
        candidate.specialization = data["specialization"]
    if "min_salary" in data:
        candidate.min_salary = data["min_salary"]
    if "formats" in data:
        candidate.formats = list(data["formats"] or [])
    if data.get("status"):
        candidate.status = data["status"]
    if data.get("visible") is not None:
        candidate.visible = bool(data["visible"])
    if "liked_skills" in data:
        candidate.liked_skills = require_skills(list(data["liked_skills"] or []))
    if "disliked_skills" in data:
        candidate.disliked_skills = require_skills(list(data["disliked_skills"] or []))
    if "liked_domains" in data:
        candidate.liked_domains = require_domains(list(data["liked_domains"] or []))
    if "blocked_domains" in data:
        candidate.blocked_domains = require_domains(list(data["blocked_domains"] or []))
    if "phone" in data:
        candidate.phone = data["phone"]
    if "contact_email" in data:
        candidate.contact_email = data["contact_email"]
    if "consent_processing" in data and data["consent_processing"] is not None:
        candidate.consent_processing = bool(data["consent_processing"])
    if "consent_publication" in data and data["consent_publication"] is not None:
        candidate.consent_publication = bool(data["consent_publication"])
    if "soft_skills" in data and data["soft_skills"] is not None:
        candidate.soft_skills = clean_soft_skills(list(data["soft_skills"]))


async def update_profile(session: AsyncSession, candidate: Candidate, body: CandidateUpdate) -> CandidateProfile:
    apply_profile_update(candidate, body.model_dump(mode="json", exclude_unset=True))
    await _touch(candidate)
    await session.flush()
    return await profile_view(session, candidate)


async def replace_skills(
    session: AsyncSession,
    candidate_id: UUID,
    source: str,
    skill_ids: list[str],
    score: float | None = None,
) -> None:
    await session.execute(
        delete(CandidateSkill).where(CandidateSkill.candidate_id == candidate_id, CandidateSkill.source == source)
    )
    for skill_id in skill_ids:
        session.add(CandidateSkill(candidate_id=candidate_id, skill_id=skill_id, source=source, score=score))
    await session.flush()


async def sync_project_skills(session: AsyncSession, candidate_id: UUID) -> None:
    rows = list(await session.scalars(select(Project).where(Project.candidate_id == candidate_id)))
    skill_ids: list[str] = []
    for row in rows:
        if row.source == "resume":
            continue
        for skill_id in row.skills or []:
            if skill_id not in skill_ids:
                skill_ids.append(skill_id)
    await replace_skills(session, candidate_id, SkillSource.project.value, skill_ids)


async def finish_evidence(session: AsyncSession, candidate_id: UUID) -> None:
    from app.profile.evidence import kick, rebuild, recompute

    await rebuild(session, candidate_id)
    await session.commit()
    await recompute(candidate_id)
    await kick(candidate_id)


async def _owned_project(session: AsyncSession, candidate_id: UUID, project_id: UUID) -> Project:
    project = await session.get(Project, project_id)
    if project is None or project.candidate_id != candidate_id:
        raise AppError("not_found", "Проект не найден", status_code=404)
    return project


def _fill_project(project: Project, body: ProjectIn, skills: list[str]) -> None:
    project.task = body.task
    project.role = body.role.value
    project.skills = skills
    project.scale = body.scale
    project.outcome = body.outcome
    project.occurred_on = as_date(body.date)
    project.url = body.url


async def list_projects(session: AsyncSession, candidate: Candidate) -> list[ProjectOut]:
    return [project_out(row) for row in await _load_projects(session, candidate.id)]


async def create_project(session: AsyncSession, candidate: Candidate, body: ProjectIn) -> ProjectOut:
    skills = require_skills(body.skills)
    project = Project(candidate_id=candidate.id, task=body.task, role=body.role.value, skills=skills, source="self")
    _fill_project(project, body, skills)
    session.add(project)
    await session.flush()
    await sync_project_skills(session, candidate.id)
    await _touch(candidate)
    await finish_evidence(session, candidate.id)
    return project_out(project)


async def update_project(session: AsyncSession, candidate: Candidate, project_id: UUID, body: ProjectIn) -> ProjectOut:
    project = await _owned_project(session, candidate.id, project_id)
    skills = require_skills(body.skills)
    _fill_project(project, body, skills)
    await session.flush()
    await sync_project_skills(session, candidate.id)
    await _touch(candidate)
    await finish_evidence(session, candidate.id)
    return project_out(project)


async def delete_project(session: AsyncSession, candidate: Candidate, project_id: UUID) -> None:
    project = await _owned_project(session, candidate.id, project_id)
    await session.delete(project)
    await session.flush()
    await sync_project_skills(session, candidate.id)
    await _touch(candidate)
    await finish_evidence(session, candidate.id)


async def link_fsp(session: AsyncSession, candidate: Candidate) -> CandidateProfile:
    user = await session.get(User, candidate.user_id)
    items = load_achievements(user.kc_sub if user else "", user.email if user else None)
    await session.execute(delete(FspAchievement).where(FspAchievement.candidate_id == candidate.id))
    skill_ids: list[str] = []
    for item in items:
        session.add(
            FspAchievement(
                candidate_id=candidate.id,
                discipline=item["discipline"],
                event=item["event"],
                place=item["place"],
                year=item["year"],
            )
        )
        for raw in [*item.get("skills", []), item["discipline"]]:
            skill_id = normalize(str(raw))
            if skill_id and skill_id not in skill_ids:
                skill_ids.append(skill_id)
    await replace_skills(session, candidate.id, SkillSource.fsp_id.value, skill_ids)
    await _touch(candidate)
    await finish_evidence(session, candidate.id)
    return await profile_view(session, candidate)


def _quoted(span: object, source: str) -> str | None:
    if not isinstance(span, str):
        return None
    text_span = span.strip()
    if text_span and text_span in source:
        return text_span
    return None


async def apply_confirmed_resume(
    session: AsyncSession,
    candidate_id: UUID,
    payload: dict[str, Any],
    raw_text: str,
) -> dict[str, Any]:
    """Store resume rows that have a quote in the source text, then rebuild evidence."""
    experiences_out: list[dict[str, Any]] = []
    await session.execute(delete(Experience).where(Experience.candidate_id == candidate_id))
    for item in payload.get("experiences") or []:
        if not isinstance(item, dict):
            continue
        span = _quoted(item.get("evidence_span"), raw_text)
        if span is None:
            continue
        company = str(item.get("company") or "")
        role = str(item.get("role") or "")
        description = str(item.get("description") or "")
        start = as_date(item.get("start") if isinstance(item.get("start"), str) else None)
        end = as_date(item.get("end") if isinstance(item.get("end"), str) else None)
        session.add(
            Experience(
                candidate_id=candidate_id,
                company=company,
                role=role,
                start=start,
                end=end,
                description=description,
                evidence_span=span,
            )
        )
        experiences_out.append(
            {
                "company": company,
                "role": role,
                "start": start.isoformat() if start else None,
                "end": end.isoformat() if end else None,
                "description": description,
                "evidence_span": span,
            }
        )

    skill_ids: list[str] = []
    skills_out: list[dict[str, Any]] = []
    for item in payload.get("skills") or []:
        if not isinstance(item, dict):
            continue
        span = _quoted(item.get("evidence_span"), raw_text)
        if span is None:
            continue
        name = str(item.get("name") or "")
        skill_id = normalize(str(item.get("skill_id") or "")) or normalize(name)
        if skill_id is None:
            continue
        if skill_id not in skill_ids:
            skill_ids.append(skill_id)
        skills_out.append({"name": name or skill_id, "skill_id": skill_id, "evidence_span": span})
    await replace_skills(session, candidate_id, SkillSource.resume.value, skill_ids)

    await session.execute(delete(Project).where(Project.candidate_id == candidate_id, Project.source == "resume"))
    projects_out: list[dict[str, Any]] = []
    for item in payload.get("projects") or []:
        if not isinstance(item, dict):
            continue
        span = _quoted(item.get("evidence_span"), raw_text)
        task = str(item.get("task") or "").strip()
        if span is None or not task:
            continue
        project_skills: list[str] = []
        for raw in item.get("skills") or []:
            skill_id = normalize(str(raw))
            if skill_id and skill_id not in project_skills:
                project_skills.append(skill_id)
        role = canonical_role(str(item.get("role") or ""))
        outcome = item.get("outcome")
        session.add(
            Project(
                candidate_id=candidate_id,
                task=task,
                role=role,
                skills=project_skills,
                outcome=str(outcome) if outcome else None,
                source="resume",
            )
        )
        projects_out.append(
            {
                "task": task,
                "role": role,
                "skills": project_skills,
                "outcome": str(outcome) if outcome else None,
                "evidence_span": span,
            }
        )
    await session.flush()
    await sync_project_skills(session, candidate_id)
    return {"experiences": experiences_out, "skills": skills_out, "projects": projects_out}


async def build_me(session: AsyncSession, principal: Principal) -> Me:
    user = await provision_user(session, principal)
    candidate_id = None
    if user.role == "candidate":
        candidate_id = (await get_or_create_candidate(session, user.id)).id
    return Me(
        sub=principal.sub,
        role=user.role,
        email=user.email,
        user_id=user.id,
        candidate_id=candidate_id,
        company_id=await _company_id(session, user.id),
    )


async def grade_view(session: AsyncSession, candidate: Candidate) -> GradeView:
    rows = await _attempt_rows(session, candidate.id)
    declared: Grade | None = None
    skill_scores: list[SkillScore] = []
    history: list[GradeHistoryItem] = []
    if rows:
        declared = _as_grade(rows[0].get("declared_grade"))
    for row in rows:
        if row.get("finished_at") is None:
            continue
        grade = _as_grade(row.get("result_grade"))
        score = row.get("score")
        if grade is None or score is None or row.get("finished_at") is None:
            continue
        if not skill_scores:
            skill_scores = _skill_scores(row.get("skill_scores"))
        history.append(
            GradeHistoryItem(
                attempt_id=row["id"],
                finished_at=row["finished_at"],
                score=float(score),
                grade=grade,
            )
        )
    specialization = None
    if candidate.specialization:
        try:
            specialization = Specialization(candidate.specialization)
        except ValueError:
            specialization = None
    return GradeView(
        specialization=specialization,
        declared_grade=declared,
        grade=_as_grade(candidate.grade),
        score=candidate.grade_score,
        ready_for_next=bool(candidate.ready_for_next),
        rank=candidate.category_rank,
        category_size=candidate.category_size,
        skill_scores=skill_scores,
        history=history,
    )


async def settings_view(candidate: Candidate) -> CandidateSettings:
    """Настройки кандидата. Поля приватности читаются через getattr, чтобы тестовые
    заглушки без новых колонок продолжали работать."""
    return CandidateSettings(
        visible=bool(candidate.visible),
        hidden_company_ids=list(candidate.hidden_company_ids or []),
        consent_processing=bool(candidate.consent_processing),
        consent_publication=bool(candidate.consent_publication),
        soft_skills=list(candidate.soft_skills or []),
        show_full_name=bool(getattr(candidate, "show_full_name", False)),
        show_current_job=bool(getattr(candidate, "show_current_job", True)),
        show_fsp=bool(getattr(candidate, "show_fsp", True)),
        show_pdf=bool(getattr(candidate, "show_pdf", True)),
        show_psych=bool(getattr(candidate, "show_psych", False)),
        consent_processing_at=getattr(candidate, "consent_processing_at", None),
        consent_publication_at=getattr(candidate, "consent_publication_at", None),
    )


async def settings_full(session: AsyncSession, candidate: Candidate) -> CandidateSettings:
    """Настройки для экрана: плюс названия скрытых компаний и признак связи с ФСП ID."""
    view = await settings_view(candidate)
    ids = list(candidate.hidden_company_ids or [])
    if ids:
        sql = text("SELECT id, name FROM companies WHERE id = ANY(:ids)")
        try:
            async with session.begin_nested():
                rows = (await session.execute(sql, {"ids": ids})).mappings().all()
        except Exception:
            logger.info("company names are unavailable for %s", candidate.id)
            rows = []
        names = {row["id"]: row["name"] or "Компания без названия" for row in rows}
        view.hidden_companies = [HiddenCompany(id=item, name=names.get(item, "Компания удалена")) for item in ids]
    view.fsp_linked = bool(await _load_achievements(session, candidate.id))
    return view


def _consent_moment(before: bool, after: bool, moment: datetime | None) -> datetime | None:
    if not after:
        return None
    if before and moment is not None:
        return moment
    return datetime.now(UTC)


async def update_settings(session: AsyncSession, candidate: Candidate, body: CandidateSettings) -> CandidateSettings:
    if hasattr(candidate, "consent_processing_at"):
        candidate.consent_processing_at = _consent_moment(
            bool(candidate.consent_processing), body.consent_processing, candidate.consent_processing_at
        )
        candidate.consent_publication_at = _consent_moment(
            bool(candidate.consent_publication), body.consent_publication, candidate.consent_publication_at
        )
    candidate.visible = body.visible
    candidate.hidden_company_ids = list(dict.fromkeys(body.hidden_company_ids))
    candidate.consent_processing = body.consent_processing
    candidate.consent_publication = body.consent_publication
    candidate.soft_skills = clean_soft_skills(body.soft_skills)
    if hasattr(candidate, "show_full_name"):
        candidate.show_full_name = body.show_full_name
        candidate.show_current_job = body.show_current_job
        candidate.show_fsp = body.show_fsp
        candidate.show_pdf = body.show_pdf
        candidate.show_psych = body.show_psych
    await _touch(candidate)
    await session.flush()
    return await settings_view(candidate)


async def set_psych_sharing(session: AsyncSession, candidate: Candidate, value: bool) -> None:
    candidate.show_psych = bool(value)
    await session.flush()


async def unlink_fsp(session: AsyncSession, candidate: Candidate) -> CandidateProfile:
    """Отвязка ФСП ID: удаляет достижения и навыки, полученные из реестра ФСП."""
    await session.execute(delete(FspAchievement).where(FspAchievement.candidate_id == candidate.id))
    await replace_skills(session, candidate.id, SkillSource.fsp_id.value, [])
    await _touch(candidate)
    await finish_evidence(session, candidate.id)
    return await profile_view(session, candidate)


# ---------------------------------------------------------------- приватность для работодателя


def _current_job(experiences: list[Experience]) -> str | None:
    if not experiences:
        return None
    open_items = [item for item in experiences if item.end is None]
    pool = open_items or experiences
    latest = max(pool, key=lambda item: item.start or date.min)
    parts = [part for part in (latest.role, latest.company) if part]
    if not parts:
        return None
    prefix = "" if latest.end is None else "Последнее место: "
    return prefix + " · ".join(parts)


async def privacy_for(session: AsyncSession, candidate_ids: list[UUID]) -> dict[UUID, dict[str, Any]]:
    """Что разрешено показать работодателю по каждому кандидату."""
    if not candidate_ids:
        return {}
    rows = list(await session.scalars(select(Candidate).where(Candidate.id.in_(candidate_ids))))
    result: dict[UUID, dict[str, Any]] = {}
    for row in rows:
        full = (row.full_name or "").strip()
        show_job = bool(row.show_current_job)
        job = None
        if show_job:
            job = _current_job(await _load_experiences(session, row.id))
        result[row.id] = {
            "visible": bool(row.visible),
            "hidden_company_ids": set(row.hidden_company_ids or []),
            "name": full if (row.show_full_name and full) else display_name(full),
            "show_full_name": bool(row.show_full_name),
            "show_fsp": bool(row.show_fsp),
            "show_pdf": bool(row.show_pdf),
            "show_psych": bool(row.show_psych),
            "current_job": job,
        }
    return result


async def employer_company_id(session: AsyncSession, principal: Principal) -> UUID | None:
    user = await provision_user(session, principal)
    return await _company_id(session, user.id)


async def basic_card(session: AsyncSession, candidate_id: UUID) -> dict[str, Any] | None:
    """Карточка кандидата из банка, когда он не попал в подборку по потребности."""
    candidate = await session.get(Candidate, candidate_id)
    if candidate is None or not candidate.visible:
        return None
    skills = await _load_skills(session, candidate.id)
    achievements = await _load_achievements(session, candidate.id)
    experiences = await _load_experiences(session, candidate.id)
    projects = await _load_projects(session, candidate.id)
    skill_ids: list[str] = []
    for item in skills:
        if item.skill_id not in skill_ids:
            skill_ids.append(item.skill_id)
    category = " · ".join(
        part for part in ((candidate.specialization or "").replace("data_ml", "Data/ML").capitalize(),
                          (candidate.grade or "").capitalize()) if part
    ) or "Категория не присвоена"
    badge = None
    if achievements:
        best = min(achievements, key=lambda item: (item.place or 99, -(item.year or 0)))
        place = f"{best.place} место · " if best.place else ""
        badge = {"discipline": best.discipline, "text": f"{place}{best.event}"}
    explanations = ["Кандидат из банка: по этой потребности он не попал в подборку, совпадение не рассчитано."]
    if candidate.grade_score is not None:
        explanations.append(f"Тест на грейд: {round(float(candidate.grade_score))} из 100")
    return {
        "candidate_id": candidate.id,
        "display_name": display_name(candidate.full_name or ""),
        "full_name_initials": display_name(candidate.full_name or ""),
        "category": category,
        "city": candidate.city,
        "experience_years": experience_years(experiences) if experiences else None,
        "match": 0,
        "test_score": None if candidate.grade_score is None else float(candidate.grade_score),
        "explanations": explanations,
        "skills": skill_ids[:12],
        "projects": [item.task for item in projects][:5],
        "fsp_badge": badge,
        "invitation_status": None,
    }


async def employer_profile_pdf(
    session: AsyncSession, candidate_id: UUID, contacts_revealed: bool
) -> bytes | None:
    """Стандартизированный PDF для работодателя с учётом приватности кандидата."""
    from app.profile.pdf import render_profile_pdf

    candidate = await session.get(Candidate, candidate_id)
    if candidate is None or not candidate.visible or not candidate.show_pdf:
        return None
    profile = await profile_view(session, candidate)
    if not candidate.show_full_name:
        profile.full_name = profile.display_name
    if not candidate.show_fsp:
        profile.fsp_achievements = []
    if not candidate.show_current_job:
        profile.experiences = []
    if not contacts_revealed:
        profile.phone = None
        profile.contact_email = None
    return render_profile_pdf(profile)


def _as_grade(value: object) -> Grade | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return Grade(value)
    except ValueError:
        return None


def _skill_scores(value: object) -> list[SkillScore]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    scores: list[SkillScore] = []
    if isinstance(value, dict):
        for key, raw in value.items():
            try:
                scores.append(SkillScore(skill_id=str(key), score=float(raw)))
            except (TypeError, ValueError):
                continue
        return scores
    if isinstance(value, list):
        for item in value:
            if not isinstance(item, dict) or "skill_id" not in item:
                continue
            try:
                scores.append(SkillScore(skill_id=str(item["skill_id"]), score=float(item["score"])))
            except (TypeError, ValueError, KeyError):
                continue
    return scores


async def _open_invites(session: AsyncSession, candidate_id: UUID) -> int:
    sql = text(
        "SELECT COUNT(*) FROM invitations WHERE candidate_id = :candidate_id AND status IN ('sent', 'viewed')"
    )
    try:
        async with session.begin_nested():
            value = (await session.execute(sql, {"candidate_id": candidate_id})).scalar_one()
    except Exception:
        logger.info("open invite count is unavailable for %s", candidate_id)
        return 0
    return int(value or 0)


async def _company_id(session: AsyncSession, user_id: UUID) -> UUID | None:
    sql = text("SELECT id FROM companies WHERE owner_user_id = :user_id")
    try:
        async with session.begin_nested():
            value = (await session.execute(sql, {"user_id": user_id})).scalar_one_or_none()
    except Exception:
        logger.info("company lookup is unavailable for %s", user_id)
        return None
    return value if isinstance(value, UUID) else None


async def _attempt_rows(session: AsyncSession, candidate_id: UUID) -> list[Any]:
    sql = text(
        "SELECT id, finished_at, score, result_grade, declared_grade, skill_scores "
        "FROM attempts WHERE candidate_id = :candidate_id ORDER BY started_at DESC"
    )
    try:
        async with session.begin_nested():
            result = await session.execute(sql, {"candidate_id": candidate_id})
            return list(result.mappings().all())
    except Exception:
        logger.info("attempt history is unavailable for %s", candidate_id)
        return []


set_candidate_hook(_candidate_hook)
bind(sys.modules[__name__])
