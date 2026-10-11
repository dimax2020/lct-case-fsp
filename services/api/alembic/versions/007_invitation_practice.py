"""Optional EPA practice attached to a career invitation.

Revision ID: 007_invitation_practice
Revises: 006_psych_privacy
Create Date: 2026-10-11
"""

from alembic import op

revision = "007_invitation_practice"
down_revision = "006_psych_privacy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE invitations
        ADD COLUMN IF NOT EXISTS practice_id VARCHAR(80),
        ADD COLUMN IF NOT EXISTS practice_title VARCHAR(200)
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE invitations DROP COLUMN IF EXISTS practice_title")
    op.execute("ALTER TABLE invitations DROP COLUMN IF EXISTS practice_id")
