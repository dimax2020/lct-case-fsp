"""CAT session state and template exposure counters.

Revision ID: 009_cat
Revises: 008_daily_tasks
Create Date: 2026-10-11
"""

from alembic import op

revision = "009_cat"
down_revision = "008_daily_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE attempts ADD COLUMN IF NOT EXISTS cat jsonb")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cat_exposure (
            template_id varchar(64) PRIMARY KEY,
            shown integer NOT NULL DEFAULT 0
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS cat_exposure")
    op.execute("ALTER TABLE attempts DROP COLUMN IF EXISTS cat")
