from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.core.enums import Benefit


class RecruiterContact(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None


class CompanyWrite(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    city: str | None = Field(default=None, max_length=120)
    size: str | None = Field(default=None, max_length=64)
    industry: str | None = Field(default=None, max_length=120)
    about: str | None = None
    recruiter_contact: RecruiterContact = Field(default_factory=RecruiterContact)
    benefits: list[Benefit] = Field(default_factory=list)

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("city", "size", "industry", "about", mode="before")
    @classmethod
    def strip_optional(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value


class CompanyOut(BaseModel):
    id: UUID
    name: str = ""
    city: str | None = None
    size: str | None = None
    industry: str | None = None
    about: str | None = None
    recruiter_contact: RecruiterContact = Field(default_factory=RecruiterContact)
    benefits: list[Benefit] = Field(default_factory=list)
