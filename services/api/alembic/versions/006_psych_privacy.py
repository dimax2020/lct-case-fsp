"""Тест рабочего стиля, настройки приватности кандидата, сайт и логотип компании.

Revision ID: 006_psych_privacy
Revises: 005_roadmap_runs
Create Date: 2026-10-11
"""

from alembic import op

revision = "006_psych_privacy"
down_revision = "005_roadmap_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS psych_attempts (
            id UUID PRIMARY KEY,
            candidate_id UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
            version VARCHAR(32) NOT NULL,
            answers JSONB NOT NULL DEFAULT '{}'::jsonb,
            result JSONB,
            started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            finished_at TIMESTAMPTZ
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_psych_attempts_candidate_id ON psych_attempts (candidate_id)")
    op.execute("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS show_full_name BOOLEAN NOT NULL DEFAULT false")
    op.execute("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS show_current_job BOOLEAN NOT NULL DEFAULT true")
    op.execute("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS show_fsp BOOLEAN NOT NULL DEFAULT true")
    op.execute("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS show_pdf BOOLEAN NOT NULL DEFAULT true")
    op.execute("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS show_psych BOOLEAN NOT NULL DEFAULT false")
    op.execute("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS consent_processing_at TIMESTAMPTZ")
    op.execute("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS consent_publication_at TIMESTAMPTZ")
    # Уже данные согласия получают дату миграции: точный момент до неё не хранился.
    op.execute("UPDATE candidates SET consent_processing_at = now() WHERE consent_processing AND consent_processing_at IS NULL")
    op.execute("UPDATE candidates SET consent_publication_at = now() WHERE consent_publication AND consent_publication_at IS NULL")
    op.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS website VARCHAR(300)")
    op.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS logo TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS logo")
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS website")
    for column in (
        "consent_publication_at",
        "consent_processing_at",
        "show_psych",
        "show_pdf",
        "show_fsp",
        "show_current_job",
        "show_full_name",
    ):
        op.execute(f"ALTER TABLE candidates DROP COLUMN IF EXISTS {column}")
    op.execute("DROP TABLE IF EXISTS psych_attempts")
