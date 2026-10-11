import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Vacancy(Base):
    __tablename__ = "vacancies"
    __table_args__ = (
        CheckConstraint("salary_to >= salary_from", name="ck_vacancies_salary"),
        CheckConstraint("status IN ('open', 'closed')", name="ck_vacancies_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    specialization: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    grades: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    salary_from: Mapped[int] = mapped_column(Integer, nullable=False)
    salary_to: Mapped[int] = mapped_column(Integer, nullable=False)
    formats: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    city: Mapped[str | None] = mapped_column(String(120))
    must_skills: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open", server_default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("vacancy_id", "candidate_id", name="uq_application_vacancy_candidate"),
        CheckConstraint("status IN ('sent', 'viewed', 'accepted', 'declined')", name="ck_applications_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vacancy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vacancies.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="sent", server_default="sent")
    message: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    decline_reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    declined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
