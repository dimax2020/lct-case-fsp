from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_serializer

from app.core.enums import GRADE_ORDER, Grade, Specialization, WorkFormat


def check_grades(grades: list[str]) -> None:
    if len(grades) not in (1, 2):
        raise ValueError("укажите один грейд или два соседних")
    parsed: list[Grade] = []
    for item in grades:
        try:
            parsed.append(Grade(item))
        except ValueError:
            raise ValueError("неизвестный грейд") from None
    if len(set(parsed)) != len(parsed):
        raise ValueError("грейды не должны повторяться")
    if len(parsed) == 2:
        distance = abs(GRADE_ORDER.index(parsed[0]) - GRADE_ORDER.index(parsed[1]))
        if distance != 1:
            raise ValueError("можно указать только два соседних грейда")


def ensure_vacancy_bounds(salary_from: int, salary_to: int, grades: list[str]) -> None:
    if salary_to < salary_from:
        raise ValueError("верх вилки меньше низа")
    check_grades(grades)


def applicant_email(contact_email: str | None, user_email: str | None) -> str | None:
    for value in (contact_email, user_email):
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def applicant_phone(phone: str | None) -> str | None:
    if isinstance(phone, str) and phone.strip():
        return phone.strip()
    return None


APPLICATION_STATUSES = ("sent", "viewed", "accepted", "declined")


def status_counts(statuses: list[str]) -> dict[str, int]:
    counts = {name: 0 for name in APPLICATION_STATUSES}
    for status in statuses:
        if status in counts:
            counts[status] += 1
    return counts


def public_application(
    *,
    application_id: UUID,
    vacancy_id: UUID,
    status: str,
    message: str,
    created_at: datetime,
    title: str,
    viewer: str,
    company_name: str | None = None,
    salary_from: int | None = None,
    salary_to: int | None = None,
    candidate_email: str | None = None,
    candidate_phone: str | None = None,
    decline_reason: str | None = None,
) -> dict[str, Any]:
    """Candidate payloads never carry contacts. Employer payloads carry only this applicant."""
    payload: dict[str, Any] = {
        "id": str(application_id),
        "vacancy_id": str(vacancy_id),
        "status": status,
        "message": message,
        "created_at": created_at.isoformat(),
        "title": title,
    }
    if decline_reason:
        payload["decline_reason"] = decline_reason
    if viewer == "candidate":
        payload["company_name"] = company_name
        payload["salary_from"] = salary_from
        payload["salary_to"] = salary_to
        return payload
    if viewer == "employer":
        payload["candidate_email"] = candidate_email
        payload["candidate_phone"] = candidate_phone
        return payload
    raise ValueError("роль не поддерживается")


class VacancyWrite(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    specialization: Specialization
    grades: list[str] = Field(min_length=1, max_length=2)
    salary_from: int = Field(ge=0)
    salary_to: int = Field(ge=0)
    formats: list[WorkFormat] = Field(min_length=1)
    city: str | None = Field(default=None, max_length=120)
    must_skills: list[str] = Field(min_length=1, max_length=12)
    description: str = Field(min_length=50)
    domain: str = Field(min_length=1, max_length=64)

    @field_validator("city")
    @classmethod
    def blank_city(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class VacancyOut(BaseModel):
    id: UUID
    company_id: UUID
    company_name: str
    title: str
    specialization: str
    grades: list[str]
    salary_from: int
    salary_to: int
    formats: list[str]
    city: str | None = None
    must_skills: list[str]
    description: str
    domain: str
    status: str


class ApplicationCreate(BaseModel):
    message: str = Field(default="", max_length=4000)


class DeclineIn(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class ApplicationOut(BaseModel):
    id: UUID
    vacancy_id: UUID
    status: str
    message: str
    created_at: datetime
    title: str
    audience: str = Field(exclude=True)
    company_name: str | None = None
    salary_from: int | None = None
    salary_to: int | None = None
    candidate_email: str | None = None
    candidate_phone: str | None = None
    decline_reason: str | None = None

    @model_serializer(mode="plain")
    def dumped(self) -> dict[str, Any]:
        return public_application(
            application_id=self.id,
            vacancy_id=self.vacancy_id,
            status=self.status,
            message=self.message,
            created_at=self.created_at,
            title=self.title,
            viewer=self.audience,
            company_name=self.company_name,
            salary_from=self.salary_from,
            salary_to=self.salary_to,
            candidate_email=self.candidate_email,
            candidate_phone=self.candidate_phone,
            decline_reason=self.decline_reason,
        )


class ApplicationList(BaseModel):
    items: list[ApplicationOut]
    counts: dict[str, int]
