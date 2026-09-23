import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session, selectinload

from app.core.audit import client_ip, record_audit_event
from app.core.database import get_db
from app.core.pagination import DEFAULT_PAGE_SIZE, Limit, Offset
from app.core.rate_limit import AUTHENTICATED_WRITE_RATE_LIMIT, limiter
from app.core.security import ClinicalPermission, get_current_clinic_id, require_permission
from app.models import AuditAction, AuditResult, Staff, User, UserRole
from app.modules.staff.schemas import StaffCreateRequest, StaffPublic, StaffUpdateRequest
from app.modules.staff.service import create_staff_member

router = APIRouter()

# See app/modules/appointments/router.py for why this is a module-level
# variable instead of an inline require_roles(...) call in the signature.
_staff_manage = require_permission(ClinicalPermission.STAFF_MANAGE)
_staff_read = require_permission(ClinicalPermission.STAFF_DIRECTORY_READ)


def _public(staff: Staff) -> StaffPublic:
    return StaffPublic(
        id=staff.id,
        clinic_id=staff.clinic_id,
        full_name=staff.user.full_name,
        staff_role=staff.staff_role,
        specialty=staff.specialty,
        license_number=staff.license_number,
        is_active=staff.user.is_active,
    )


def _visible_staff(db: Session, staff_id: uuid.UUID, admin: User) -> Staff:
    staff = (
        db.query(Staff)
        .options(selectinload(Staff.user))
        .filter(Staff.id == staff_id, Staff.clinic_id == admin.clinic_id)
        .first()
    )
    if staff is None:
        raise HTTPException(status_code=404, detail="Profissional não encontrado.")
    return staff


@router.post("", response_model=StaffPublic, status_code=201)
@limiter.limit(AUTHENTICATED_WRITE_RATE_LIMIT)
def create(
    request: Request,
    payload: StaffCreateRequest,
    db: Session = Depends(get_db),
    clinic_id: str = Depends(get_current_clinic_id),
    _admin: User = Depends(_staff_manage),
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
    return _public(staff)


@router.get("", response_model=list[StaffPublic])
def list_mine(
    limit: Limit = DEFAULT_PAGE_SIZE,
    offset: Offset = 0,
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    clinic_id: str = Depends(get_current_clinic_id),
    user: User = Depends(_staff_read),
) -> list[StaffPublic]:
    """
    Staff directory for the caller's own clinic. Open to any authenticated
    role in the clinic (patients included) — this is "who are our doctors",
    not sensitive clinical data, and staff/clinic_admin need it to pick a
    staff member when creating an appointment.
    """
    query = db.query(Staff).options(selectinload(Staff.user)).filter(Staff.clinic_id == clinic_id)
    if include_inactive:
        if user.role != UserRole.CLINIC_ADMIN:
            raise HTTPException(status_code=403, detail="Sem permissões para listar contas inativas.")
    else:
        query = query.join(User, Staff.user_id == User.id).filter(User.is_active.is_(True))
    return [_public(s) for s in query.order_by(Staff.created_at).offset(offset).limit(limit).all()]


@router.patch("/{staff_id}", response_model=StaffPublic)
def update(
    staff_id: uuid.UUID,
    payload: StaffUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(_staff_manage),
) -> StaffPublic:
    staff = _visible_staff(db, staff_id, admin)
    values = payload.model_dump(exclude_unset=True)
    if "full_name" in values:
        staff.user.full_name = values.pop("full_name")
    for key, value in values.items():
        setattr(staff, key, value)
    db.commit()
    db.refresh(staff)
    _audit_lifecycle(request, admin, AuditAction.STAFF_UPDATED, staff.id)
    return _public(staff)


@router.post("/{staff_id}/deactivate", response_model=StaffPublic)
def deactivate(
    staff_id: uuid.UUID, request: Request, db: Session = Depends(get_db), admin: User = Depends(_staff_manage)
) -> StaffPublic:
    staff = _visible_staff(db, staff_id, admin)
    if not staff.user.is_active:
        raise HTTPException(status_code=409, detail="Profissional já está inativo.")
    staff.user.is_active = False
    staff.user.token_epoch += 1
    db.commit()
    db.refresh(staff)
    _audit_lifecycle(request, admin, AuditAction.STAFF_DEACTIVATED, staff.id)
    return _public(staff)


@router.post("/{staff_id}/reactivate", response_model=StaffPublic)
def reactivate(
    staff_id: uuid.UUID, request: Request, db: Session = Depends(get_db), admin: User = Depends(_staff_manage)
) -> StaffPublic:
    staff = _visible_staff(db, staff_id, admin)
    if staff.user.is_active:
        raise HTTPException(status_code=409, detail="Profissional já está ativo.")
    staff.user.is_active = True
    staff.user.token_epoch += 1
    db.commit()
    db.refresh(staff)
    _audit_lifecycle(request, admin, AuditAction.STAFF_REACTIVATED, staff.id)
    return _public(staff)


def _audit_lifecycle(request: Request, admin: User, action: AuditAction, staff_id: uuid.UUID) -> None:
    record_audit_event(
        action=action,
        result=AuditResult.SUCCESS,
        clinic_id=admin.clinic_id,
        actor_user_id=admin.id,
        actor_email=admin.email,
        resource_type="staff",
        resource_id=staff_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
