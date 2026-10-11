"""Map ORM rows to the profile response models."""

from app.core.enums import CandidateStatus, Grade, ProjectRole, SkillSource, Specialization, WorkFormat
from app.profile.models import Candidate, CandidateSkill, Experience, FspAchievement, Project
from app.profile.parsing import as_datetime, display_name, in_pool_eligible
from app.profile.schemas import (
    CandidateProfile,
    ExperienceOut,
    FspAchievementOut,
    ProjectOut,
    SkillOut,
)


def _specialization(value: str | None) -> Specialization | None:
    if not value:
        return None
    try:
        return Specialization(value)
    except ValueError:
        return None


def _grade(value: str | None) -> Grade | None:
    if not value:
        return None
    try:
        return Grade(value)
    except ValueError:
        return None


def _formats(values: list[str] | None) -> list[WorkFormat]:
    parsed: list[WorkFormat] = []
    for value in values or []:
        try:
            parsed.append(WorkFormat(value))
        except ValueError:
            continue
    return parsed


def project_out(row: Project) -> ProjectOut:
    return ProjectOut(
        id=row.id,
        task=row.task,
        role=ProjectRole(row.role),
        skills=list(row.skills or []),
        scale=row.scale,
        outcome=row.outcome,
        date=as_datetime(row.occurred_on),
        url=row.url,
        source=row.source,
    )


def experience_out(row: Experience) -> ExperienceOut:
    return ExperienceOut(
        id=row.id,
        company=row.company,
        role=row.role,
        start=as_datetime(row.start),
        end=as_datetime(row.end),
        description=row.description or "",
        evidence_span=row.evidence_span,
    )


def achievement_out(row: FspAchievement) -> FspAchievementOut:
    return FspAchievementOut(
        id=row.id,
        discipline=row.discipline,
        event=row.event,
        place=row.place,
        year=row.year,
    )


def skill_out(row: CandidateSkill) -> SkillOut:
    try:
        source = SkillSource(row.source)
    except ValueError:
        source = SkillSource.project
    return SkillOut(skill_id=row.skill_id, score=row.score, source=source)


def candidate_profile(
    candidate: Candidate,
    skills: list[CandidateSkill],
    projects: list[Project],
    experiences: list[Experience],
    achievements: list[FspAchievement],
) -> CandidateProfile:
    status = candidate.status if candidate.status in {item.value for item in CandidateStatus} else CandidateStatus.paused.value
    return CandidateProfile(
        id=candidate.id,
        full_name=candidate.full_name or "",
        display_name=display_name(candidate.full_name or ""),
        city=candidate.city,
        specialization=_specialization(candidate.specialization),
        grade=_grade(candidate.grade),
        grade_score=candidate.grade_score,
        ready_for_next=bool(candidate.ready_for_next),
        category_rank=candidate.category_rank,
        category_size=candidate.category_size,
        min_salary=candidate.min_salary,
        formats=_formats(list(candidate.formats or [])),
        status=CandidateStatus(status),
        visible=bool(candidate.visible),
        in_pool_eligible=in_pool_eligible(candidate.min_salary, list(candidate.formats or [])),
        liked_skills=list(candidate.liked_skills or []),
        disliked_skills=list(candidate.disliked_skills or []),
        liked_domains=list(candidate.liked_domains or []),
        blocked_domains=list(candidate.blocked_domains or []),
        last_active_at=candidate.last_active_at,
        phone=candidate.phone,
        contact_email=candidate.contact_email,
        consent_processing=bool(candidate.consent_processing),
        consent_publication=bool(candidate.consent_publication),
        soft_skills=list(candidate.soft_skills or []),
        skills=[skill_out(row) for row in skills],
        projects=[project_out(row) for row in projects],
        experiences=[experience_out(row) for row in experiences],
        fsp_achievements=[achievement_out(row) for row in achievements],
    )
