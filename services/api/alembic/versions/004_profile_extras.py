"""Add candidate consents and soft skills.

Revision ID: 004_profile_extras
Revises: 003_grade_policy
Create Date: 2026-10-11
"""

from alembic import op

revision = "004_profile_extras"
down_revision = "003_grade_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS consent_processing BOOLEAN NOT NULL DEFAULT false")
    op.execute("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS consent_publication BOOLEAN NOT NULL DEFAULT false")
    op.execute("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS soft_skills TEXT[] NOT NULL DEFAULT '{}'")


def downgrade() -> None:
    op.execute("ALTER TABLE candidates DROP COLUMN IF EXISTS soft_skills")
    op.execute("ALTER TABLE candidates DROP COLUMN IF EXISTS consent_publication")
    op.execute("ALTER TABLE candidates DROP COLUMN IF EXISTS consent_processing")
