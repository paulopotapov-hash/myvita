from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.audit import client_ip, record_audit_event
from app.core.database import get_db
from app.core.security import get_current_clinic_id, get_current_user, require_roles
from app.models import Appointment, AuditAction, AuditResult, User, UserRole
from app.modules.appointments.schemas import AppointmentCreateRequest, AppointmentPublic
from app.modules.appointments.service import create_appointment, list_appointments_for_user

router = APIRouter()

# require_roles(...) is called once here, at import time (a dependency
# factory returning a closure) — never per-request. Named module-level so
# the linter (and readers) don't mistake it for a mutable default re-evaluated
# on every call, which is the actual footgun B008 exists to catch.
_staff_or_admin_only = require_roles(UserRole.STAFF, UserRole.CLINIC_ADMIN)


@router.post(
    "",
    response_model=AppointmentPublic,
    status_code=201,
    dependencies=[],
)
def create(
    request: Request,
    payload: AppointmentCreateRequest,
    db: Session = Depends(get_db),
    clinic_id: str = Depends(get_current_clinic_id),
    _staff_user: User = Depends(_staff_or_admin_only),
) -> Appointment:
    appointment = create_appointment(db, clinic_id, payload)
    record_audit_event(
        action=AuditAction.APPOINTMENT_CREATED,
        result=AuditResult.SUCCESS,
        clinic_id=clinic_id,
        actor_user_id=_staff_user.id,
        actor_email=_staff_user.email,
        resource_type="appointment",
        resource_id=appointment.id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return appointment


@router.get("", response_model=list[AppointmentPublic])
def list_mine(
    request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[Appointment]:
    """
    Patients get their own appointments; staff/clinic_admin get every
    appointment in their own clinic. Scoping happens entirely server-side
    based on the authenticated session — see service.list_appointments_for_user.
    """
    appointments = list_appointments_for_user(db, user)
    # Clinical access log: who looked at appointment data, and whose.
    # One row per request (not per appointment) — the "resource" for this
    # event is "the appointment list this user is entitled to see", not
    # each individual row, which would flood the table for no
    # investigative benefit.
    record_audit_event(
        action=(
            AuditAction.PATIENT_VIEWED_OWN_RECORD
            if user.role == UserRole.PATIENT
            else AuditAction.STAFF_VIEWED_APPOINTMENT
        ),
        result=AuditResult.SUCCESS,
        clinic_id=user.clinic_id,
        actor_user_id=user.id,
        actor_email=user.email,
        resource_type="appointment_list",
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        metadata={"count": len(appointments)},
    )
    return appointments
