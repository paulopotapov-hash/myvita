import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.core.database import Base  # noqa: E402
from app import models  # noqa: E402,F401  (imported for side-effect: registers tables on Base.metadata)

config = context.config
# Migrations run as the schema owner; the application itself should connect
# with a least-privilege runtime role (see app/db_provisioning.py). When
# MIGRATION_DATABASE_URL is unset (local development), both are the same.
migration_url = os.environ.get("MIGRATION_DATABASE_URL") or settings.DATABASE_URL
# configparser treats "%" as interpolation syntax; URL-encoded passwords need escaping.
config.set_main_option("sqlalchemy.url", migration_url.replace("%", "%%"))

if config.config_file_name is not None:
    # Keep application loggers (and their test captures) intact when Alembic
    # is invoked programmatically, e.g. by the test suite's schema setup.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata
# Deprecated tables kept on purpose are ignored by autogenerate (see app/core/schema_policy.py).
from app.core.schema_policy import include_object  # noqa: E402


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
