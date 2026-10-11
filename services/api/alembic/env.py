import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.assessment import models as assessment_models  # noqa: F401
from app.chat import models as chat_models  # noqa: F401
from app.company import models as company_models  # noqa: F401
from app.core.db import Base
from app.core.models import Job, User  # noqa: F401
from app.core.settings import get_settings
from app.invitation import models as invitation_models  # noqa: F401
from app.need import models as need_models  # noqa: F401
from app.profile import models as profile_models  # noqa: F401
from app.psych import models as psych_models  # noqa: F401
from app.resume import models as resume_models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().postgres_dsn)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=get_settings().postgres_dsn, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    section = config.get_section(config.config_ini_section) or {}
    connectable = async_engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
