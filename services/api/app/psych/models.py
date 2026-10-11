import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class PsychAttempt(Base):
    """Прохождение теста рабочего стиля. Ответы сохраняются черновиком после каждого шага."""

    __tablename__ = "psych_attempts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    answers: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    result: Mapped[dict | None] = mapped_column(JSONB)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
