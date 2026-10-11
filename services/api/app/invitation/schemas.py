from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.enums import ContactChannel, DeclineReason, InvitationStatus


class InvitationCreate(BaseModel):
    need_id: UUID
    candidate_id: UUID
    title: str = Field(min_length=1)
    message: str = ""
    salary_from: int = Field(ge=0)
    salary_to: int = Field(ge=0)
    contact_channel: ContactChannel
    contact_value: str = Field(min_length=1)
    deadline: datetime | None = None


class InvitationOut(BaseModel):
    id: UUID
    need_id: UUID
    candidate_id: UUID
    status: InvitationStatus
    title: str
    message: str
    salary_from: int
    salary_to: int
    contact_channel: ContactChannel | None = None
    deadline: datetime | None = None
    decline_reason: DeclineReason | None = None
    created_at: datetime
    company_name: str | None = None
    need_title: str | None = None
    candidate_display_name: str | None = None
    candidate_email: str | None = None
    candidate_phone: str | None = None
    recruiter_contact: str | None = None


class InvitationList(BaseModel):
    items: list[InvitationOut]
    counts: dict[str, int]


class DeclineIn(BaseModel):
    reason: DeclineReason


class FavoriteOut(BaseModel):
    candidate_id: UUID
    favorite: bool
