import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core.audit import audit_denials, client_ip, record_audit_event
from app.core.clinical_access import ClinicalAction, clinical_access, has_role_action, staff_profile
from app.core.database import get_db
from app.core.rate_limit import AUTHENTICATED_WRITE_RATE_LIMIT, limiter
from app.core.security import get_current_clinic_id, get_current_user, require_roles
from app.models import (
    AppointmentRequest,
    AppointmentRequestStatus,
    AuditAction,
    AuditResult,
    Staff,
    StaffRole,
    User,
    UserRole,
)
from app.modules.appointment_requests.schemas import (
    AppointmentRequestAccept,
    AppointmentRequestCreate,
    AppointmentRequestPublic,
)
from app.modules.appointment_requests.service import (
    accept_request,
    cancel_own_request,
    create_request,
    list_for_clinic,
    list_for_patient,
    patient_name,
    reject_request,
    request_patient_id,
)

router = APIRouter()
_patient_only = require_roles(UserRole.PATIENT)
# Same roles that schedule appointments today (POST /appointments).
_scheduler_only = require_roles(UserRole.STAFF, UserRole.CLINIC_ADMIN)
_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"description": "Not a request of the caller's clinic (or, for patients, not their own)."},
    409: {"description": "The request is no longer pending."},
}


def _clinician_scope(db: Session, user: User) -> Staff | None:
    """Mirror of POST /appointments: clinic admins and administrative staff schedule
    for any patient of the clinic (None); clinicians only within their care team."""
    if user.role != UserRole.STAFF:
        return None
    staff = staff_profile(db, user)
    if staff is None or not has_role_action(staff.staff_role, ClinicalAction.VIEW_APPOINTMENTS):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissões clínicas.")
    return None if staff.staff_role == StaffRole.ADMIN else staff


def _require_decision_access(
    http_request: Request, db: Session, user: User, request_id: uuid.UUID, clinic_id: uuid.UUID
) -> None:
    if _clinician_scope(db, user) is None:
        return
    with audit_denials(http_request, user, "appointment_request", request_id):
        patient_id = request_patient_id(db, request_id, clinic_id)
        clinical_access(db, patient_id, user, ClinicalAction.EDIT_APPOINTMENTS)


def _public(request: AppointmentRequest, name: str, *, may_read_reason: bool) -> AppointmentRequestPublic:
    return AppointmentRequestPublic(
        id=request.id,
        clinic_id=request.clinic_id,
        patient_id=request.patient_id,
        patient_name=name,
        preferred_start=request.preferred_start,
        reason=request.reason if may_read_reason else None,
        status=request.status,
        appointment_id=request.appointment_id,
        decided_at=request.decided_at,
        created_at=request.created_at,
    )


def _may_read_reason(user: User, db: Session) -> bool:
    if user.role == UserRole.PATIENT:
        return True
    staff = staff_profile(db, user)
    return staff is not None and has_role_action(staff.staff_role, ClinicalAction.VIEW_APPOINTMENT_REASON)


def _audit(
    http_request: Request,
    actor: User,
    action: AuditAction,
    request: AppointmentRequest,
    extra: dict[str, Any] | None = None,
) -> None:
    # Identifiers only — never the reason text.
    record_audit_event(
        action=action,
        result=AuditResult.SUCCESS,
        clinic_id=request.clinic_id,
        actor_user_id=actor.id,
        actor_email=actor.email,
        resource_type="appointment_request",
        resource_id=request.id,
        ip_address=client_ip(http_request),
        user_agent=http_request.headers.get("user-agent"),
        metadata={"patient_id": str(request.patient_id), **(extra or {})},
    )


@router.post("", response_model=AppointmentRequestPublic, status_code=status.HTTP_201_CREATED)
@limiter.limit(AUTHENTICATED_WRITE_RATE_LIMIT)
def create(
    payload: AppointmentRequestCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(_patient_only),
) -> AppointmentRequestPublic:
    """Patient requests an appointment for themselves (identity and clinic from the session)."""
    created = create_request(db, user, payload)
    _audit(request, user, AuditAction.APPOINTMENT_REQUEST_CREATED, created)
    return _public(created, user.full_name, may_read_reason=True)


@router.get("", response_model=list[AppointmentRequestPublic])
def list_requests(
    response: Response,
    request_status: AppointmentRequestStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[AppointmentRequestPublic]:
    """Patients: their own requests (any status). Staff/clinic admins: their clinic's
    requests, pending by default (`status` filter). Total in `X-Total-Count`."""
    offset = (page - 1) * page_size
    if user.role == UserRole.PATIENT:
        rows, total = list_for_patient(db, user, offset=offset, limit=page_size)
    else:
        clinic_id = get_current_clinic_id(user)
        clinician = _clinician_scope(db, user)
        rows, total = list_for_clinic(
            db,
            uuid.UUID(str(clinic_id)),
            request_status or AppointmentRequestStatus.PENDING,
            offset=offset,
            limit=page_size,
            assigned_to_staff_id=clinician.id if clinician is not None else None,
        )
    response.headers["X-Total-Count"] = str(total)
    may_read_reason = _may_read_reason(user, db)
    return [_public(row, name, may_read_reason=may_read_reason) for row, name in rows]


@router.post("/{request_id}/accept", response_model=AppointmentRequestPublic, responses=_NOT_FOUND)
@limiter.limit(AUTHENTICATED_WRITE_RATE_LIMIT)
def accept(
    request_id: uuid.UUID,
    payload: AppointmentRequestAccept,
    request: Request,
    db: Session = Depends(get_db),
    clinic_id: str = Depends(get_current_clinic_id),
    user: User = Depends(_scheduler_only),
) -> AppointmentRequestPublic:
    """Accept a pending request: creates the appointment with the chosen professional
    and slot (existing overlap and tenant checks apply; 409 on overlap or if already processed)."""
    _require_decision_access(request, db, user, request_id, uuid.UUID(str(clinic_id)))
    accepted, appointment = accept_request(db, request_id, uuid.UUID(str(clinic_id)), user, payload)
    _audit(request, user, AuditAction.APPOINTMENT_REQUEST_ACCEPTED, accepted, {"appointment_id": str(appointment.id)})
    record_audit_event(
        action=AuditAction.APPOINTMENT_CREATED,
        result=AuditResult.SUCCESS,
        clinic_id=appointment.clinic_id,
        actor_user_id=user.id,
        actor_email=user.email,
        resource_type="appointment",
        resource_id=appointment.id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return _public(accepted, patient_name(db, accepted), may_read_reason=_may_read_reason(user, db))


@router.post("/{request_id}/reject", response_model=AppointmentRequestPublic, responses=_NOT_FOUND)
@limiter.limit(AUTHENTICATED_WRITE_RATE_LIMIT)
def reject(
    request_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    clinic_id: str = Depends(get_current_clinic_id),
    user: User = Depends(_scheduler_only),
) -> AppointmentRequestPublic:
    _require_decision_access(request, db, user, request_id, uuid.UUID(str(clinic_id)))
    rejected = reject_request(db, request_id, uuid.UUID(str(clinic_id)), user)
    _audit(request, user, AuditAction.APPOINTMENT_REQUEST_REJECTED, rejected)
    return _public(rejected, patient_name(db, rejected), may_read_reason=_may_read_reason(user, db))


@router.post("/{request_id}/cancel", response_model=AppointmentRequestPublic, responses=_NOT_FOUND)
@limiter.limit(AUTHENTICATED_WRITE_RATE_LIMIT)
def cancel(
    request_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(_patient_only),
) -> AppointmentRequestPublic:
    """Patient withdraws their own pending request."""
    cancelled = cancel_own_request(db, request_id, user)
    _audit(request, user, AuditAction.APPOINTMENT_REQUEST_CANCELLED, cancelled)
    return _public(cancelled, user.full_name, may_read_reason=True)
