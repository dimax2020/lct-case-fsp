"""Roadmap grade probes.

Revision ID: 005_roadmap_runs
Revises: 004_profile_extras
Create Date: 2026-10-11
"""

from alembic import op

revision = "005_roadmap_runs"
down_revision = "004_profile_extras"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS roadmap_runs (
            id uuid PRIMARY KEY,
            candidate_id uuid NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
            specialization varchar(32) NOT NULL,
            declared_grade varchar(32) NOT NULL,
            level varchar(32) NOT NULL,
            latent double precision NOT NULL,
            probe_ids jsonb NOT NULL,
            step_index integer NOT NULL DEFAULT 0,
            phase varchar(16) NOT NULL DEFAULT 'checks',
            finished_at timestamptz,
            score double precision,
            measured_grade varchar(32),
            outcome varchar(16),
            cooldown_days integer,
            locked_until timestamptz,
            message text,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_roadmap_runs_candidate_id ON roadmap_runs (candidate_id)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS roadmap_steps (
            id uuid PRIMARY KEY,
            run_id uuid NOT NULL REFERENCES roadmap_runs(id) ON DELETE CASCADE,
            probe_id varchar(64) NOT NULL,
            level varchar(32) NOT NULL,
            checks jsonb,
            concrete text,
            block_score double precision,
            CONSTRAINT uq_roadmap_step UNIQUE (run_id, probe_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_roadmap_steps_run_id ON roadmap_steps (run_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS roadmap_steps")
    op.execute("DROP TABLE IF EXISTS roadmap_runs")
