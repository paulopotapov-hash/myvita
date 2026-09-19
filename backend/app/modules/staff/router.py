from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.audit import client_ip, record_audit_event
from app.core.database import get_db
from app.core.rate_limit import AUTHENTICATED_WRITE_RATE_LIMIT, limiter
from app.core.security import get_current_clinic_id, require_roles
from app.models import AuditAction, AuditResult, User, UserRole
from app.modules.staff.schemas import StaffCreateRequest, StaffPublic
from app.modules.staff.service import create_staff_member

router = APIRouter()

# See app/modules/appointments/router.py for why this is a module-level
# variable instead of an inline require_roles(...) call in the signature.
_clinic_admin_only = require_roles(UserRole.CLINIC_ADMIN)


@router.post("", response_model=StaffPublic, status_code=201)
@limiter.limit(AUTHENTICATED_WRITE_RATE_LIMIT)
def create(
    request: Request,
    payload: StaffCreateRequest,
    db: Session = Depends(get_db),
    clinic_id: str = Depends(get_current_clinic_id),
    _admin: User = Depends(_clinic_admin_only),
) -> StaffPublic:
    staff = create_staff_member(db, clinic_id, payload)
    record_audit_event(
        action=AuditAction.STAFF_CREATED,
        result=AuditResult.SUCCESS,
        clinic_id=clinic_id,
        actor_user_id=_admin.id,
        actor_email=_admin.email,
        resource_type="staff",
        resource_id=staff.id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return StaffPublic(
        id=staff.id,
        clinic_id=staff.clinic_id,
        full_name=payload.full_name,
        staff_role=staff.staff_role,
        specialty=staff.specialty,
    )
