from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.core.enums import Benefit


LOGO_MAX_CHARS = 400_000
LOGO_PREFIXES = ("data:image/png;base64,", "data:image/jpeg;base64,", "data:image/webp;base64,")


class CompanyBrief(BaseModel):
    """Поиск компании кандидатом, чтобы скрыть от неё профиль."""

    id: UUID
    name: str
    city: str | None = None


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
    website: str | None = Field(default=None, max_length=300)
    logo: str | None = Field(default=None, max_length=LOGO_MAX_CHARS)

    @field_validator("website", mode="before")
    @classmethod
    def clean_website(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        text = value.strip()
        if not text:
            return None
        if not text.startswith(("http://", "https://")):
            text = "https://" + text
        if " " in text or "." not in text:
            raise ValueError("укажите адрес сайта, например company.ru")
        return text

    @field_validator("logo", mode="before")
    @classmethod
    def clean_logo(cls, value: object) -> object:
        if value is None or value == "":
            return None
        if not isinstance(value, str) or not value.startswith(LOGO_PREFIXES):
            raise ValueError("логотип — картинка PNG, JPEG или WebP")
        return value

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
    website: str | None = None
    logo: str | None = None
    name: str = ""
    city: str | None = None
    size: str | None = None
    industry: str | None = None
    about: str | None = None
    recruiter_contact: RecruiterContact = Field(default_factory=RecruiterContact)
    benefits: list[Benefit] = Field(default_factory=list)
