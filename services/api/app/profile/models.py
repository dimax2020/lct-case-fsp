import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import EMBEDDING_DIM, Base


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), default="", server_default="")
    city: Mapped[str | None] = mapped_column(String(120))
    specialization: Mapped[str | None] = mapped_column(String(32), index=True)
    grade: Mapped[str | None] = mapped_column(String(32))
    grade_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    grade_score: Mapped[float | None] = mapped_column(Float)
    ready_for_next: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    category_rank: Mapped[int | None] = mapped_column(Integer)
    category_size: Mapped[int | None] = mapped_column(Integer)
    min_salary: Mapped[int | None] = mapped_column(Integer)
    formats: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list, server_default="{}")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="paused", server_default="paused")
    visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    liked_skills: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list, server_default="{}")
    disliked_skills: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list, server_default="{}")
    liked_domains: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list, server_default="{}")
    blocked_domains: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list, server_default="{}")
    hidden_company_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list, server_default="{}"
    )
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    phone: Mapped[str | None] = mapped_column(String(32))
    contact_email: Mapped[str | None] = mapped_column(String(320))
    consent_processing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    consent_publication: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    soft_skills: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list, server_default="{}")
    # Что видит работодатель (настройки приватности кандидата).
    show_full_name: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    show_current_job: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    show_fsp: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    show_pdf: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    show_psych: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    consent_processing_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consent_publication_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CandidateSkill(Base):
    __tablename__ = "candidate_skills"
    __table_args__ = (UniqueConstraint("candidate_id", "skill_id", "source", name="uq_candidate_skill_source"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    skill_id: Mapped[str] = mapped_column(String(64), nullable=False)
    score: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(32), nullable=False)


class Experience(Base):
    __tablename__ = "experiences"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    company: Mapped[str] = mapped_column(String(200), default="")
    role: Mapped[str] = mapped_column(String(200), default="")
    start: Mapped[date | None] = mapped_column(Date)
    end: Mapped[date | None] = mapped_column(Date)
    description: Mapped[str] = mapped_column(Text, default="")
    evidence_span: Mapped[str | None] = mapped_column(Text)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    task: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    skills: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list, server_default="{}")
    scale: Mapped[str | None] = mapped_column(String(200))
    outcome: Mapped[str | None] = mapped_column(Text)
    occurred_on: Mapped[date | None] = mapped_column("date", Date)
    url: Mapped[str | None] = mapped_column(String(500))
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="self", server_default="self")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvidenceUnit(Base):
    __tablename__ = "evidence_units"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    origin: Mapped[str] = mapped_column(String(32), nullable=False)
    origin_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    task: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str | None] = mapped_column(String(64))
    skills: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list, server_default="{}")
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="participant", server_default="participant")
    occurred_on: Mapped[date | None] = mapped_column("date", Date)
    trust: Mapped[float] = mapped_column(Float, nullable=False, default=0.35)
    evidence_span: Mapped[str | None] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))


class DailyTaskAnswer(Base):
    __tablename__ = "daily_task_answers"
    __table_args__ = (UniqueConstraint("candidate_id", "day", name="uq_daily_task_day"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    skill_id: Mapped[str] = mapped_column(String(64), nullable=False)
    skill_label: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    boost_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FspAchievement(Base):
    __tablename__ = "fsp_achievements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    discipline: Mapped[str] = mapped_column(String(64), nullable=False)
    event: Mapped[str] = mapped_column(String(200), nullable=False)
    place: Mapped[int | None] = mapped_column(Integer)
    year: Mapped[int | None] = mapped_column(Integer)
