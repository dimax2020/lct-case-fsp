from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.core.enums import RequirementKind, Specialization, WorkFormat, grade_distance


class NeedWrite(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    specialization: Specialization
    grades: list[str] = Field(min_length=1, max_length=2)
    salary_from: int = Field(ge=0)
    salary_to: int = Field(ge=0)
    formats: list[WorkFormat] = Field(min_length=1)
    city: str | None = None
    must_skills: list[str] = Field(min_length=1, max_length=5)
    nice_skills: list[str] = Field(default_factory=list, max_length=5)
    description: str = Field(min_length=300)
    domain: str = Field(min_length=1)
    stages: int = Field(ge=1, le=10)

    @model_validator(mode="after")
    def check_bounds(self) -> "NeedWrite":
        if self.salary_to < self.salary_from:
            raise ValueError("верх вилки меньше низа")
        if len(self.grades) == 2 and grade_distance(self.grades[0], self.grades[1]) != 1:
            raise ValueError("можно указать только два соседних грейда")
        overlap = set(self.must_skills) & set(self.nice_skills)
        if overlap:
            raise ValueError("навык не может быть и обязательным, и желательным")
        return self


class NeedOut(NeedWrite):
    id: UUID
    status: str
    company_id: UUID


class RequirementOut(BaseModel):
    id: UUID | None = None
    task: str
    domain: str | None = None
    skills: list[str] = Field(default_factory=list)
    scale: str | None = None
    kind: RequirementKind
    evidence_span: str | None = None


class CategorySuggestion(BaseModel):
    specialization: Specialization
    grades: list[str]
    domain: str | None = None
    evidence_span: str | None = None


class ParseResult(BaseModel):
    category: CategorySuggestion | None = None
    requirements: list[RequirementOut] = Field(default_factory=list)
    llm_used: bool


class MatchAccepted(BaseModel):
    job_id: UUID


class FspBadge(BaseModel):
    discipline: str
    text: str


class MatchFactors(BaseModel):
    """Составляющие соответствия в процентах: из чего сложился скор кандидата."""

    skills: int = 0
    experience: int = 0
    grade: int = 0
    tests: int = 0
    fsp: int = 0
    fresh: int = 0
    conditions: int = 0


class SkillCoverage(BaseModel):
    skill: str
    value: int = Field(ge=0, le=100)


class ShortlistItemOut(BaseModel):
    position: int
    candidate_id: UUID
    display_name: str
    category: str
    grade: str | None = None
    experience_years: float | None = None
    city: str | None = None
    fsp_badge: FspBadge | None = None
    match: int = Field(ge=0, le=100)
    test_score: float | None = None
    explanations: list[str] = Field(default_factory=list)
    invitation_status: str | None = None
    favorite: bool = False
    skills: list[str] = Field(default_factory=list)
    tested_skills: list[str] = Field(default_factory=list)
    formats: list[str] = Field(default_factory=list)
    last_active_at: str | None = None
    factors: MatchFactors | None = None
    must_coverage: list[SkillCoverage] = Field(default_factory=list)


class CategoryTileOut(BaseModel):
    id: str
    title: str
    count: int


class ShortlistOut(BaseModel):
    need_id: UUID
    total: int
    page: int
    page_size: int
    categories: list[CategoryTileOut] = Field(default_factory=list)
    items: list[ShortlistItemOut] = Field(default_factory=list)
    hidden_count: int = 0


class CandidateCard(BaseModel):
    candidate_id: UUID
    display_name: str
    full_name_initials: str
    category: str
    city: str | None = None
    experience_years: float | None = None
    match: int
    test_score: float | None = None
    explanations: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    fsp_badge: FspBadge | None = None
    invitation_status: str | None = None
    contacts_revealed: bool = False
    email: str | None = None
    phone: str | None = None
    # Настройки приватности кандидата и происхождение карточки.
    in_shortlist: bool = True
    current_job: str | None = None
    pdf_available: bool = False
    psych_available: bool = False
    daily_stories: list[dict[str, Any]] = Field(default_factory=list)
