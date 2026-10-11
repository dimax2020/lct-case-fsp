import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), default="", server_default="")
    city: Mapped[str | None] = mapped_column(String(120))
    size: Mapped[str | None] = mapped_column(String(64))
    industry: Mapped[str | None] = mapped_column(String(120))
    about: Mapped[str | None] = mapped_column(Text)
    website: Mapped[str | None] = mapped_column(String(300))
    # Логотип хранится как data URL (PNG/JPEG/WebP до ~300 КБ), чтобы не поднимать отдельное файловое хранилище.
    logo: Mapped[str | None] = mapped_column(Text)
    recruiter_contact: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    benefits: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
