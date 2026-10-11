import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class TaskBank(Base):
    __tablename__ = "tasks_bank"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    specialization: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    skills: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list, server_default="{}")
    difficulty: Mapped[int] = mapped_column(Integer, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list | None] = mapped_column(JSONB)
    answer: Mapped[str | None] = mapped_column(Text)
    tests_public: Mapped[list | None] = mapped_column(JSONB)
    tests_hidden: Mapped[list | None] = mapped_column(JSONB)
    languages: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list, server_default="{}")


class Attempt(Base):
    __tablename__ = "attempts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    specialization: Mapped[str] = mapped_column(String(32), nullable=False)
    declared_grade: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    score: Mapped[float | None] = mapped_column(Float)
    skill_scores: Mapped[dict | None] = mapped_column(JSONB)
    result_grade: Mapped[str | None] = mapped_column(String(32))
    ready_for_next: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    grade_change: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    cat: Mapped[dict | None] = mapped_column(JSONB)


class AttemptAnswer(Base):
    __tablename__ = "attempt_answers"
    __table_args__ = (UniqueConstraint("attempt_id", "task_id", name="uq_attempt_task"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attempt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("attempts.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks_bank.id"), nullable=False)
    answer: Mapped[str | None] = mapped_column(Text)
    code: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(32))
    verdict: Mapped[str | None] = mapped_column(String(32))
    passed: Mapped[int | None] = mapped_column(Integer)
    total: Mapped[int | None] = mapped_column(Integer)
    skipped: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CatExposure(Base):
    __tablename__ = "cat_exposure"

    template_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    shown: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class MicroTask(Base):
    __tablename__ = "micro_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    need_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("needs.id", ondelete="SET NULL"))
    is_open: Mapped[bool] = mapped_column("open", Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RoadmapRun(Base):
    __tablename__ = "roadmap_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    specialization: Mapped[str] = mapped_column(String(32), nullable=False)
    declared_grade: Mapped[str] = mapped_column(String(32), nullable=False)
    level: Mapped[str] = mapped_column(String(32), nullable=False)
    latent: Mapped[float] = mapped_column(Float, nullable=False)
    probe_ids: Mapped[list] = mapped_column(JSONB, nullable=False)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    phase: Mapped[str] = mapped_column(String(16), nullable=False, default="checks", server_default="checks")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    score: Mapped[float | None] = mapped_column(Float)
    measured_grade: Mapped[str | None] = mapped_column(String(32))
    outcome: Mapped[str | None] = mapped_column(String(16))
    cooldown_days: Mapped[int | None] = mapped_column(Integer)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RoadmapStep(Base):
    __tablename__ = "roadmap_steps"
    __table_args__ = (UniqueConstraint("run_id", "probe_id", name="uq_roadmap_step"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roadmap_runs.id", ondelete="CASCADE"), index=True)
    probe_id: Mapped[str] = mapped_column(String(64), nullable=False)
    level: Mapped[str] = mapped_column(String(32), nullable=False)
    checks: Mapped[dict | None] = mapped_column(JSONB)
    concrete: Mapped[str | None] = mapped_column(Text)
    block_score: Mapped[float | None] = mapped_column(Float)


class MicroAnswer(Base):
    __tablename__ = "micro_answers"
    __table_args__ = (UniqueConstraint("task_id", "candidate_id", name="uq_micro_answer"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("micro_tasks.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
