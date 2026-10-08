import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core.audit import audit_request
from app.core.database import get_db
from app.core.security import require_roles
from app.models import AuditAction, AuditLog, User, UserRole
from app.modules.audit_logs.schemas import AuditActorPublic, AuditLogPublic
from app.modules.audit_logs.service import AuditLogFilters, list_audit_logs, resolve_actor_names

router = APIRouter()
_clinic_admin_only = require_roles(UserRole.CLINIC_ADMIN)


def _public(row: AuditLog, names: dict[uuid.UUID, str]) -> AuditLogPublic:
    return AuditLogPublic(
        id=row.id,
        timestamp=row.timestamp,
        actor=AuditActorPublic(
            user_id=row.actor_user_id,
            email=row.actor_email,
            name=names.get(row.actor_user_id) if row.actor_user_id else None,
        ),
        action=row.action,
        result=row.result,
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        ip_address=row.ip_address,
        request_id=row.request_id,
        metadata=row.event_metadata,
    )


@router.get("", response_model=list[AuditLogPublic])
def list_for_clinic(
    request: Request,
    response: Response,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    actor_user_id: uuid.UUID | None = Query(default=None),
    action: AuditAction | None = Query(default=None),
    resource_type: str | None = Query(default=None, min_length=1, max_length=50, pattern=r"^[a-z_]+$"),
    resource_id: uuid.UUID | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
    admin: User = Depends(_clinic_admin_only),
) -> list[AuditLogPublic]:
    """Clinic administrators read their own clinic's audit trail, newest first.

    The clinic is always the caller's own; there is deliberately no clinic
    parameter. Reading the trail is itself recorded as AUDIT_LOG_VIEWED.
    """
    if admin.clinic_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Conta sem clínica associada.")
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Intervalo de datas inválido."
        )
    filters = AuditLogFilters(
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        date_from=date_from,
        date_to=date_to,
    )
    rows, total = list_audit_logs(
        db, admin.clinic_id, filters, offset=(page - 1) * page_size, limit=page_size
    )
    response.headers["X-Total-Count"] = str(total)
    names = resolve_actor_names(db, admin.clinic_id, rows)
    audit_request(
        request,
        action=AuditAction.AUDIT_LOG_VIEWED,
        actor=admin,
        resource_type="audit_log",
        metadata={"count": len(rows), "filters": filters.as_metadata()},
    )
    return [_public(row, names) for row in rows]
