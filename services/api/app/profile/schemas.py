from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.enums import CandidateStatus, Grade, ProjectRole, SkillSource, Specialization, WorkFormat


class SkillOut(BaseModel):
    skill_id: str
    score: float | None = None
    source: SkillSource


class ProjectIn(BaseModel):
    task: str = Field(min_length=1)
    role: ProjectRole
    skills: list[str] = Field(min_length=1)
    scale: str | None = None
    outcome: str | None = None
    date: datetime | None = None
    url: str | None = None


class ProjectOut(ProjectIn):
    id: UUID
    source: str


class ExperienceOut(BaseModel):
    id: UUID
    company: str
    role: str
    start: datetime | None = None
    end: datetime | None = None
    description: str
    evidence_span: str | None = None


class FspAchievementOut(BaseModel):
    id: UUID
    discipline: str
    event: str
    place: int | None = None
    year: int | None = None


class DailyStory(BaseModel):
    id: UUID
    day: date
    skill_id: str
    skill_label: str
    prompt: str
    answer: str
    answered_at: datetime
    boost_until: datetime


class DailyTaskIn(BaseModel):
    answer: str = Field(min_length=40, max_length=4000)


class DailyTaskView(BaseModel):
    day: date
    prompt: str
    skill_id: str
    skill_label: str
    hint: str
    answered: bool
    answer: str | None = None
    boost_active: bool
    boost_until: datetime | None = None
    stories: list[DailyStory] = Field(default_factory=list)


class CandidateUpdate(BaseModel):
    full_name: str | None = None
    city: str | None = None
    specialization: Specialization | None = None
    min_salary: int | None = Field(default=None, ge=0)
    formats: list[WorkFormat] | None = None
    status: CandidateStatus | None = None
    visible: bool | None = None
    liked_skills: list[str] | None = None
    disliked_skills: list[str] | None = None
    liked_domains: list[str] | None = None
    blocked_domains: list[str] | None = None
    phone: str | None = None
    contact_email: str | None = None
    consent_processing: bool | None = None
    consent_publication: bool | None = None
    soft_skills: list[str] | None = None


class HiddenCompany(BaseModel):
    id: UUID
    name: str


class CandidateSettings(BaseModel):
    visible: bool
    hidden_company_ids: list[UUID] = Field(default_factory=list)
    consent_processing: bool = False
    consent_publication: bool = False
    soft_skills: list[str] = Field(default_factory=list)
    show_full_name: bool = False
    show_current_job: bool = True
    show_fsp: bool = True
    show_pdf: bool = True
    show_psych: bool = False
    # Только для чтения: время, когда согласие было дано, и названия скрытых компаний.
    consent_processing_at: datetime | None = None
    consent_publication_at: datetime | None = None
    hidden_companies: list[HiddenCompany] = Field(default_factory=list)
    fsp_linked: bool = False


class CandidateProfile(BaseModel):
    id: UUID
    full_name: str
    display_name: str
    city: str | None = None
    specialization: Specialization | None = None
    grade: Grade | None = None
    grade_score: float | None = None
    ready_for_next: bool = False
    category_rank: int | None = None
    category_size: int | None = None
    min_salary: int | None = None
    formats: list[WorkFormat] = Field(default_factory=list)
    status: CandidateStatus
    visible: bool
    in_pool_eligible: bool
    liked_skills: list[str] = Field(default_factory=list)
    disliked_skills: list[str] = Field(default_factory=list)
    liked_domains: list[str] = Field(default_factory=list)
    blocked_domains: list[str] = Field(default_factory=list)
    last_active_at: datetime | None = None
    phone: str | None = None
    contact_email: str | None = None
    consent_processing: bool = False
    consent_publication: bool = False
    soft_skills: list[str] = Field(default_factory=list)
    skills: list[SkillOut] = Field(default_factory=list)
    projects: list[ProjectOut] = Field(default_factory=list)
    experiences: list[ExperienceOut] = Field(default_factory=list)
    fsp_achievements: list[FspAchievementOut] = Field(default_factory=list)
    daily_stories: list[DailyStory] = Field(default_factory=list)


class CandidateBankItem(BaseModel):
    """Employer bank card. Contacts stay off this payload."""

    id: UUID
    display_name: str
    specialization: str | None = None
    grade: str | None = None
    city: str | None = None
    skills: list[str] = Field(default_factory=list)
    has_fsp: bool
    test_score: float | None = None


class SkillScore(BaseModel):
    skill_id: str
    score: float


class GradeHistoryItem(BaseModel):
    attempt_id: UUID
    finished_at: datetime
    score: float
    grade: Grade


class GradeView(BaseModel):
    specialization: Specialization | None = None
    declared_grade: Grade | None = None
    grade: Grade | None = None
    score: float | None = None
    ready_for_next: bool = False
    rank: int | None = None
    category_size: int | None = None
    skill_scores: list[SkillScore] = Field(default_factory=list)
    history: list[GradeHistoryItem] = Field(default_factory=list)


class Me(BaseModel):
    sub: str
    role: str
    email: str | None = None
    user_id: UUID | None = None
    candidate_id: UUID | None = None
    company_id: UUID | None = None
