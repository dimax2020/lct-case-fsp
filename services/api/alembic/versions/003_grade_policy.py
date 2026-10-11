"""Grade policy and short employer tasks.

Revision ID: 003_grade_policy
Revises: 001_initial
Create Date: 2026-10-11
"""

from alembic import op

revision = "003_grade_policy"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS grade_changed_at timestamptz")
    op.execute("ALTER TABLE attempts ADD COLUMN IF NOT EXISTS grade_change boolean NOT NULL DEFAULT false")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS micro_tasks (
            id uuid PRIMARY KEY,
            title text NOT NULL,
            body text NOT NULL,
            need_id uuid REFERENCES needs(id) ON DELETE SET NULL,
            open boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS micro_answers (
            id uuid PRIMARY KEY,
            task_id uuid NOT NULL REFERENCES micro_tasks(id) ON DELETE CASCADE,
            candidate_id uuid NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
            answer text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_micro_answer UNIQUE (task_id, candidate_id)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS micro_answers")
    op.execute("DROP TABLE IF EXISTS micro_tasks")
    op.execute("ALTER TABLE attempts DROP COLUMN IF EXISTS grade_change")
    op.execute("ALTER TABLE candidates DROP COLUMN IF EXISTS grade_changed_at")
