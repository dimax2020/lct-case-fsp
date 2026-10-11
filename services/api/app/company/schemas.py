from uuid import UUID

from pydantic import BaseModel, Field

from app.core.enums import Benefit


class RecruiterContact(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None


class CompanyWrite(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    city: str | None = None
    size: str | None = None
    industry: str | None = None
    about: str | None = None
    recruiter_contact: RecruiterContact = Field(default_factory=RecruiterContact)
    benefits: list[Benefit] = Field(default_factory=list)


class CompanyOut(CompanyWrite):
    id: UUID
