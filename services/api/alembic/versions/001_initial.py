"""Initial schema.

Revision ID: 001_initial
Revises:
Create Date: 2026-10-11
"""

from alembic import op

from app.assessment import models as assessment_models  # noqa: F401
from app.chat import models as chat_models  # noqa: F401
from app.company import models as company_models  # noqa: F401
from app.core.db import Base
from app.core.models import Job, User  # noqa: F401
from app.invitation import models as invitation_models  # noqa: F401
from app.need import models as need_models  # noqa: F401
from app.profile import models as profile_models  # noqa: F401
from app.resume import models as resume_models  # noqa: F401

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    bind = op.get_bind()
    Base.metadata.create_all(bind)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_evidence_embedding "
        "ON evidence_units USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_need_req_embedding "
        "ON need_requirements USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind())
    op.execute("DROP EXTENSION IF EXISTS vector")
