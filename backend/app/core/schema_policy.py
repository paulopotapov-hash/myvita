"""Schema objects that exist in the database on purpose but have no ORM model.

DEPRECATED tables kept by integration decision (see _integration/open-items.md):
Parent A's old messaging/documents tables and the notification-target archive
created by migration 5a6b7c8d9e0f. Autogenerate would otherwise propose dropping
them. They must only ever be dropped by an explicit, reviewed migration once no
environment holds data in them; remove a name here in that same migration.
"""

from typing import Any

DEPRECATED_TABLES = frozenset(
    {
        "clinical_conversations",
        "clinical_messages",
        "clinical_documents",
        "clinical_document_versions",
        "deprecated_notification_targets",
    }
)


def include_object(obj: Any, name: str | None, type_: str, reflected: bool, compare_to: Any) -> bool:
    """Alembic `include_object` hook: ignore reflected deprecated tables (and their indexes)."""
    table_name = name if type_ == "table" else getattr(getattr(obj, "table", None), "name", None)
    return not (reflected and compare_to is None and table_name in DEPRECATED_TABLES)
