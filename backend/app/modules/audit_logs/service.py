import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditAction, AuditLog, User


@dataclass(frozen=True)
class AuditLogFilters:
    actor_user_id: uuid.UUID | None = None
    action: AuditAction | None = None
    resource_type: str | None = None
    resource_id: uuid.UUID | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None

    def as_metadata(self) -> dict[str, str]:
        """Which filters an administrator used — identifiers only, for the AUDIT_LOG_VIEWED row."""
        return {
            key: str(value)
            for key, value in (
                ("actor_user_id", self.actor_user_id),
                ("action", self.action.value if self.action else None),
                ("resource_type", self.resource_type),
                ("resource_id", self.resource_id),
                ("date_from", self.date_from.isoformat() if self.date_from else None),
                ("date_to", self.date_to.isoformat() if self.date_to else None),
            )
            if value is not None
        }


def list_audit_logs(
    db: Session, clinic_id: uuid.UUID, filters: AuditLogFilters, *, offset: int, limit: int
) -> tuple[list[AuditLog], int]:
    """Clinic-scoped, newest first. `clinic_id` MUST come from the caller's session."""
    query = db.query(AuditLog).filter(AuditLog.clinic_id == clinic_id)
    if filters.actor_user_id is not None:
        query = query.filter(AuditLog.actor_user_id == filters.actor_user_id)
    if filters.action is not None:
        query = query.filter(AuditLog.action == filters.action)
    if filters.resource_type is not None:
        query = query.filter(AuditLog.resource_type == filters.resource_type)
    if filters.resource_id is not None:
        query = query.filter(AuditLog.resource_id == filters.resource_id)
    if filters.date_from is not None:
        query = query.filter(AuditLog.timestamp >= filters.date_from)
    if filters.date_to is not None:
        query = query.filter(AuditLog.timestamp <= filters.date_to)
    total = query.count()
    rows = query.order_by(AuditLog.timestamp.desc(), AuditLog.id.desc()).offset(offset).limit(limit).all()
    return rows, total


def resolve_actor_names(db: Session, clinic_id: uuid.UUID, rows: list[AuditLog]) -> dict[uuid.UUID, str]:
    """Current display names for the actors on one page, in a single query.

    Scoped to `clinic_id` so a cross-clinic actor id (which cannot appear in a
    correctly scoped listing anyway) never resolves. Missing ids simply have no
    entry: deleted users fall back to the historical `actor_email`.
    """
    ids = {row.actor_user_id for row in rows if row.actor_user_id is not None}
    if not ids:
        return {}
    stmt = select(User.id, User.full_name).where(User.id.in_(ids), User.clinic_id == clinic_id)
    return {user_id: full_name for user_id, full_name in db.execute(stmt)}
