"""Vacancies and applications.

Revision ID: 002_vacancies
Revises: 001_initial
Create Date: 2026-10-11
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "002_vacancies"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vacancies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("specialization", sa.String(length=32), nullable=False),
        sa.Column("grades", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("salary_from", sa.Integer(), nullable=False),
        sa.Column("salary_to", sa.Integer(), nullable=False),
        sa.Column("formats", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("must_skills", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("domain", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("salary_to >= salary_from", name="ck_vacancies_salary"),
        sa.CheckConstraint("status IN ('open', 'closed')", name="ck_vacancies_status"),
    )
    op.create_index("ix_vacancies_company_id", "vacancies", ["company_id"])
    op.create_index("ix_vacancies_specialization", "vacancies", ["specialization"])
    op.create_table(
        "applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("vacancy_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vacancies.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "candidate_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="sent"),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("decline_reason", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("viewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("declined_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('sent', 'viewed', 'accepted', 'declined')", name="ck_applications_status"),
        sa.UniqueConstraint("vacancy_id", "candidate_id", name="uq_application_vacancy_candidate"),
    )
    op.create_index("ix_applications_vacancy_id", "applications", ["vacancy_id"])
    op.create_index("ix_applications_candidate_id", "applications", ["candidate_id"])


def downgrade() -> None:
    op.drop_index("ix_applications_candidate_id", table_name="applications")
    op.drop_index("ix_applications_vacancy_id", table_name="applications")
    op.drop_table("applications")
    op.drop_index("ix_vacancies_specialization", table_name="vacancies")
    op.drop_index("ix_vacancies_company_id", table_name="vacancies")
    op.drop_table("vacancies")
