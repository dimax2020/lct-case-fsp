from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.enums import ProjectRole, ResumeStatus


class EvidenceField(BaseModel):
    evidence_span: str = Field(min_length=1)


class ParsedExperience(EvidenceField):
    company: str
    role: str
    start: datetime | None = None
    end: datetime | None = None
    description: str = ""


class ParsedSkill(EvidenceField):
    name: str
    skill_id: str | None = None


class ParsedProject(EvidenceField):
    task: str
    role: ProjectRole = ProjectRole.participant
    skills: list[str] = Field(default_factory=list)
    outcome: str | None = None


class ParsedResume(BaseModel):
    experiences: list[ParsedExperience] = Field(default_factory=list)
    skills: list[ParsedSkill] = Field(default_factory=list)
    projects: list[ParsedProject] = Field(default_factory=list)


class ResumeUploadOut(BaseModel):
    resume_id: UUID
    status: ResumeStatus


class ResumeView(BaseModel):
    id: UUID
    status: ResumeStatus
    error: str | None = None
    parsed: ParsedResume | None = None
