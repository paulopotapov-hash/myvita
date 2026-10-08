import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core.audit import client_ip, record_audit_event
from app.core.clinical_access import is_clinical_staff
from app.core.database import get_db
from app.core.security import get_current_clinic_id, get_current_user, require_roles
from app.models import Appointment, AuditAction, AuditResult, Patient, Staff, User, UserRole
from app.modules.appointments.schemas import (
    AppointmentCreateRequest,
    AppointmentPublic,
    AppointmentUpdateRequest,
)
from app.modules.appointments.service import (
    cancel_appointment,
    create_appointment,
    get_appointment_for_clinic,
    list_appointments_for_user,
    update_appointment,
)

router = APIRouter()

# require_roles(...) is called once here, at import time (a dependency
# factory returning a closure) — never per-request. Named module-level so
# the linter (and readers) don't mistake it for a mutable default re-evaluated
# on every call, which is the actual footgun B008 exists to catch.
_staff_or_admin_only = require_roles(UserRole.STAFF, UserRole.CLINIC_ADMIN)


def _may_read_reason(user: User, db: Session) -> bool:
    return user.role == UserRole.PATIENT or is_clinical_staff(db, user)


def _public(
    appointment: Appointment, user: User, db: Session, *, may_read_reason: bool | None = None
) -> AppointmentPublic:
    if may_read_reason is None:
        may_read_reason = _may_read_reason(user, db)
    return AppointmentPublic(
        id=appointment.id,
        clinic_id=appointment.clinic_id,
        patient_id=appointment.patient_id,
        staff_id=appointment.staff_id,
        scheduled_at=appointment.scheduled_at,
        duration_minutes=appointment.duration_minutes,
        status=appointment.status,
        reason=appointment.reason if may_read_reason else None,
    )


def _reject_admin_reason(
    payload: AppointmentCreateRequest | AppointmentUpdateRequest, user: User, db: Session
) -> None:
    if "reason" in payload.model_fields_set and not is_clinical_staff(db, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas profissionais clínicos podem registar o motivo da consulta.",
        )


def _hide_cross_tenant_targets(payload: AppointmentCreateRequest, clinic_id: str, db: Session) -> None:
    patient = db.get(Patient, payload.patient_id)
    if patient is None or str(patient.clinic_id) != str(clinic_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Paciente não encontrado nesta clínica."
        )
    staff = db.get(Staff, payload.staff_id)
    if staff is None or str(staff.clinic_id) != str(clinic_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Profissional não encontrado nesta clínica."
        )


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
) -> AppointmentPublic:
    _hide_cross_tenant_targets(payload, clinic_id, db)
    _reject_admin_reason(payload, _staff_user, db)
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
    return _public(appointment, _staff_user, db)


@router.get("", response_model=list[AppointmentPublic])
def list_mine(
    request: Request,
    response: Response,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[AppointmentPublic]:
    """
    Patients get their own appointments; staff/clinic_admin get every
    appointment in their own clinic. Scoping happens entirely server-side
    based on the authenticated session — see service.list_appointments_for_user.
    """
    appointments, total = list_appointments_for_user(db, user, offset=(page - 1) * page_size, limit=page_size)
    response.headers["X-Total-Count"] = str(total)
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
    may_read_reason = _may_read_reason(user, db)  # once per request, not once per row
    return [_public(appointment, user, db, may_read_reason=may_read_reason) for appointment in appointments]


@router.get("/{appointment_id}", response_model=AppointmentPublic)
def detail(
    appointment_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    clinic_id: str = Depends(get_current_clinic_id),
    _user: User = Depends(get_current_user),
) -> AppointmentPublic:
    appointment = get_appointment_for_clinic(db, appointment_id, clinic_id)
    if _user.role == UserRole.PATIENT:
        patient = db.query(Patient).filter(Patient.user_id == _user.id).first()
        if patient is None or appointment.patient_id != patient.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consulta não encontrada.")
    record_audit_event(
        action=(
            AuditAction.PATIENT_VIEWED_OWN_RECORD
            if _user.role == UserRole.PATIENT
            else AuditAction.STAFF_VIEWED_APPOINTMENT
        ),
        result=AuditResult.SUCCESS,
        clinic_id=_user.clinic_id,
        actor_user_id=_user.id,
        actor_email=_user.email,
        resource_type="appointment",
        resource_id=appointment.id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return _public(appointment, _user, db)


@router.patch("/{appointment_id}", response_model=AppointmentPublic)
def update(
    appointment_id: uuid.UUID,
    payload: AppointmentUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    clinic_id: str = Depends(get_current_clinic_id),
    staff_user: User = Depends(_staff_or_admin_only),
) -> AppointmentPublic:
    get_appointment_for_clinic(db, appointment_id, clinic_id)
    _reject_admin_reason(payload, staff_user, db)
    appointment = update_appointment(db, appointment_id, clinic_id, payload)
    record_audit_event(
        action=AuditAction.APPOINTMENT_UPDATED,
        result=AuditResult.SUCCESS,
        clinic_id=clinic_id,
        actor_user_id=staff_user.id,
        actor_email=staff_user.email,
        resource_type="appointment",
        resource_id=appointment.id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return _public(appointment, staff_user, db)


@router.post("/{appointment_id}/cancel", response_model=AppointmentPublic)
def cancel(
    appointment_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    clinic_id: str = Depends(get_current_clinic_id),
    staff_user: User = Depends(_staff_or_admin_only),
) -> AppointmentPublic:
    appointment = cancel_appointment(db, appointment_id, clinic_id)
    record_audit_event(
        action=AuditAction.APPOINTMENT_CANCELLED,
        result=AuditResult.SUCCESS,
        clinic_id=clinic_id,
        actor_user_id=staff_user.id,
        actor_email=staff_user.email,
        resource_type="appointment",
        resource_id=appointment.id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return _public(appointment, staff_user, db)
