"""Phase 5.3 guard: the ORM models and the Alembic migrations describe the same schema.

The test database is built by `alembic upgrade head` (see conftest), so an empty
autogenerate diff here means models == migrations. Deprecated tables kept on purpose
are ignored through the same hook env.py uses (app/core/schema_policy.py).
"""

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect

from app import models  # noqa: F401  (registers every table on Base.metadata)
from app.core.database import Base
from app.core.schema_policy import DEPRECATED_TABLES, include_object


def test_autogenerate_diff_against_head_is_empty(engine):
    with engine.connect() as connection:
        context = MigrationContext.configure(
            connection, opts={"compare_type": True, "include_object": include_object}
        )
        diff = compare_metadata(context, Base.metadata)
    assert diff == [], diff


def test_deprecated_tables_are_kept_and_unmapped(engine):
    """Decision: Parent A's old messaging/documents tables are NOT dropped in this merge."""
    existing = set(inspect(engine).get_table_names())
    assert DEPRECATED_TABLES <= existing
    assert not (DEPRECATED_TABLES & set(Base.metadata.tables))
