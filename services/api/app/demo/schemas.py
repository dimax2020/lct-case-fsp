from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.core.enums import JobStatus


class JobOut(BaseModel):
    id: UUID
    status: JobStatus
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime | None = None


class ReseedOut(BaseModel):
    candidates: int
    companies: int
    needs: int
    invitations: int
