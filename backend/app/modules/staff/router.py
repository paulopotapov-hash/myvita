import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session, selectinload

from app.core.audit import audit_request
from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import AUTHENTICATED_WRITE_RATE_LIMIT, limiter
from app.core.security import get_current_clinic_id, get_current_user, require_roles
from app.models import AuditAction, Staff, User, UserRole
from app.modules.staff.schemas import StaffCreateRequest, StaffPublic, StaffRoleUpdateRequest
from app.modules.staff.service import (
    activate_staff_member,
    create_staff_member,
    deactivate_staff_member,
    update_staff_role,
)

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
    if not settings.ALLOW_DIRECT_STAFF_CREATION:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Criação direta desativada. Utilize um convite seguro.",
        )
    staff = create_staff_member(db, clinic_id, payload)
    audit_request(
        request, action=AuditAction.STAFF_CREATED, actor=_admin, resource_type="staff", resource_id=staff.id
    )
    return StaffPublic(
        id=staff.id,
        clinic_id=staff.clinic_id,
        full_name=payload.full_name,
        staff_role=staff.staff_role,
        specialty=staff.specialty,
        is_active=staff.user.is_active,
    )


@router.get("", response_model=list[StaffPublic])
def list_mine(
    db: Session = Depends(get_db),
    clinic_id: str = Depends(get_current_clinic_id),
    _user: User = Depends(get_current_user),
) -> list[StaffPublic]:
    """
    Staff directory for the caller's own clinic. Open to any authenticated
    role in the clinic (patients included) — this is "who are our doctors",
    not sensitive clinical data, and staff/clinic_admin need it to pick a
    staff member when creating an appointment.
    """
    staff_members = (
        db.query(Staff).options(selectinload(Staff.user)).filter(Staff.clinic_id == clinic_id).all()
    )
    return [
        StaffPublic(
            id=s.id,
            clinic_id=s.clinic_id,
            full_name=s.user.full_name,
            staff_role=s.staff_role,
            specialty=s.specialty,
            is_active=s.user.is_active,
        )
        for s in staff_members
    ]


@router.post("/{staff_id}/deactivate", response_model=StaffPublic)
@limiter.limit(AUTHENTICATED_WRITE_RATE_LIMIT)
def deactivate(
    staff_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    clinic_id: str = Depends(get_current_clinic_id),
    admin: User = Depends(_clinic_admin_only),
) -> StaffPublic:
    staff = deactivate_staff_member(db, staff_id, clinic_id, admin.id)
    audit_request(
        request,
        action=AuditAction.USER_DISABLED,
        actor=admin,
        resource_type="user",
        resource_id=staff.user_id,
    )
    return StaffPublic(
        id=staff.id,
        clinic_id=staff.clinic_id,
        full_name=staff.user.full_name,
        staff_role=staff.staff_role,
        specialty=staff.specialty,
        is_active=staff.user.is_active,
    )


@router.post("/{staff_id}/activate", response_model=StaffPublic)
@limiter.limit(AUTHENTICATED_WRITE_RATE_LIMIT)
def activate(
    staff_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    clinic_id: str = Depends(get_current_clinic_id),
    admin: User = Depends(_clinic_admin_only),
) -> StaffPublic:
    staff = activate_staff_member(db, staff_id, clinic_id)
    audit_request(
        request,
        action=AuditAction.STAFF_UPDATED,
        actor=admin,
        resource_type="user",
        resource_id=staff.user_id,
        metadata={"active": True},
    )
    return StaffPublic(
        id=staff.id,
        clinic_id=staff.clinic_id,
        full_name=staff.user.full_name,
        staff_role=staff.staff_role,
        specialty=staff.specialty,
        is_active=staff.user.is_active,
    )


@router.patch("/{staff_id}/role", response_model=StaffPublic)
@limiter.limit(AUTHENTICATED_WRITE_RATE_LIMIT)
def change_role(
    staff_id: uuid.UUID,
    payload: StaffRoleUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    clinic_id: str = Depends(get_current_clinic_id),
    admin: User = Depends(_clinic_admin_only),
) -> StaffPublic:
    staff = update_staff_role(db, staff_id, clinic_id, payload)
    audit_request(
        request,
        action=AuditAction.STAFF_UPDATED,
        actor=admin,
        resource_type="staff",
        resource_id=staff.id,
        metadata={"staff_role": staff.staff_role.value},
    )
    return StaffPublic(
        id=staff.id,
        clinic_id=staff.clinic_id,
        full_name=staff.user.full_name,
        staff_role=staff.staff_role,
        specialty=staff.specialty,
        is_active=staff.user.is_active,
    )
