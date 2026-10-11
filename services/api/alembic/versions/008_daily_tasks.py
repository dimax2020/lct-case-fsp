"""Daily skill stories and next-day shortlist boost.

Revision ID: 008_daily_tasks
Revises: 007_invitation_practice
Create Date: 2026-10-11
"""

from alembic import op

revision = "008_daily_tasks"
down_revision = "007_invitation_practice"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_task_answers (
            id uuid PRIMARY KEY,
            candidate_id uuid NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
            day date NOT NULL,
            skill_id varchar(64) NOT NULL,
            skill_label varchar(80) NOT NULL,
            prompt text NOT NULL,
            answer text NOT NULL,
            boost_until timestamptz NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_daily_task_day ON daily_task_answers (candidate_id, day)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_daily_task_answers_candidate_id ON daily_task_answers (candidate_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS daily_task_answers")
