from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.enums import HiringStage, MessageKind


class Slot(BaseModel):
    start: datetime
    end: datetime


class MessageCreate(BaseModel):
    kind: MessageKind = MessageKind.text
    body: str = ""
    slots: list[Slot] | None = None
    hiring_stage: HiringStage | None = None


class MessageOut(BaseModel):
    id: UUID
    author_user_id: UUID
    kind: MessageKind
    body: str
    slots: list[Slot] | None = None
    hiring_stage: HiringStage | None = None
    created_at: datetime


class MessageList(BaseModel):
    items: list[MessageOut] = Field(default_factory=list)
