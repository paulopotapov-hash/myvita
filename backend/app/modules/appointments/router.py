import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.core.audit import client_ip, record_audit_event
from app.core.database import get_db
from app.core.pagination import DEFAULT_PAGE_SIZE, Limit, Offset
from app.core.security import (
    ClinicalPermission,
    get_current_clinic_id,
    get_current_user,
    has_permission,
    require_permission,
)
from app.models import Appointment, AppointmentStatus, AuditAction, AuditResult, Patient, User, UserRole
from app.modules.appointments.schemas import (
    AppointmentCreateRequest,
    AppointmentPublic,
    AppointmentUpdateRequest,
)
from app.modules.appointments.service import (
    create_appointment,
    list_appointments_for_user,
    validate_slot,
    validate_status_transition,
)
from app.modules.clinical.service import create_notification

router = APIRouter()

# require_roles(...) is called once here, at import time (a dependency
# factory returning a closure) — never per-request. Named module-level so
# the linter (and readers) don't mistake it for a mutable default re-evaluated
# on every call, which is the actual footgun B008 exists to catch.
_appointment_manage = require_permission(ClinicalPermission.APPOINTMENT_MANAGE)
_appointment_read = require_permission(ClinicalPermission.APPOINTMENT_READ)


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
    _staff_user: User = Depends(_appointment_manage),
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
    request: Request,
    limit: Limit = DEFAULT_PAGE_SIZE,
    offset: Offset = 0,
    patient_id: uuid.UUID | None = None,
    staff_id: uuid.UUID | None = None,
    status: AppointmentStatus | None = None,
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(_appointment_read),
) -> list[Appointment]:
    """
    Patients get their own appointments; staff/clinic_admin get every
    appointment in their own clinic. Scoping happens entirely server-side
    based on the authenticated session — see service.list_appointments_for_user.
    """
    for value in (start_date, end_date):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise HTTPException(status_code=422, detail="As datas dos filtros devem incluir timezone.")
    if start_date is not None and end_date is not None and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date deve ser anterior ou igual a end_date.")
    appointments = list_appointments_for_user(
        db,
        user,
        limit,
        offset,
        patient_id=patient_id,
        staff_id=staff_id,
        appointment_status=status,
        start_date=start_date,
        end_date=end_date,
    )
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


def _visible_appointment(db: Session, item_id: uuid.UUID, user: User) -> Appointment:
    item = (
        db.query(Appointment)
        .filter(Appointment.id == item_id, Appointment.clinic_id == user.clinic_id)
        .first()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Consulta não encontrada.")
    if user.role == UserRole.PATIENT:
        patient = db.query(Patient).filter(Patient.id == item.patient_id, Patient.user_id == user.id).first()
        if patient is None:
            raise HTTPException(status_code=404, detail="Consulta não encontrada.")
    return item


@router.get("/{item_id}", response_model=AppointmentPublic)
def detail(
    item_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(_appointment_read),
) -> Appointment:
    item = _visible_appointment(db, item_id, user)
    record_audit_event(
        action=AuditAction.STAFF_VIEWED_APPOINTMENT
        if user.role != UserRole.PATIENT
        else AuditAction.PATIENT_VIEWED_OWN_RECORD,
        result=AuditResult.SUCCESS,
        clinic_id=user.clinic_id,
        actor_user_id=user.id,
        actor_email=user.email,
        resource_type="appointment",
        resource_id=item.id,
        ip_address=client_ip(request),
    )
    return item


@router.patch("/{item_id}", response_model=AppointmentPublic)
def update(
    item_id: uuid.UUID,
    payload: AppointmentUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(_appointment_manage),
) -> Appointment:
    item = _visible_appointment(db, item_id, user)
    values = payload.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=422, detail="Indique pelo menos um campo para alterar.")
    if "status" in values and values["status"] is None:
        raise HTTPException(status_code=422, detail="Estado obrigatório.")
    requested_status = values.get("status")
    if requested_status is not None and requested_status != item.status:
        validate_status_transition(item.status, requested_status)
    changed_values = {key: value for key, value in values.items() if getattr(item, key) != value}
    if not changed_values:
        return item
    if changed_values.get("status") == AppointmentStatus.CANCELLED:
        return _cancel_appointment(item, request, db, user)
    if "scheduled_at" in changed_values or "duration_minutes" in changed_values:
        start = changed_values.get("scheduled_at", item.scheduled_at)
        duration = changed_values.get("duration_minutes", item.duration_minutes)
        if start is None or duration is None:
            raise HTTPException(status_code=422, detail="Data e duração obrigatórias.")
        validate_slot(db, str(user.clinic_id), item.staff_id, start, duration, item.id)
    for key, value in changed_values.items():
        setattr(item, key, value)
    _notify_appointment_parties(
        db, item, user, "Consulta alterada", "Uma consulta foi alterada.", "appointment_updated"
    )
    db.commit()
    db.refresh(item)
    record_audit_event(
        action=AuditAction.APPOINTMENT_UPDATED,
        result=AuditResult.SUCCESS,
        clinic_id=user.clinic_id,
        actor_user_id=user.id,
        actor_email=user.email,
        resource_type="appointment",
        resource_id=item.id,
        ip_address=client_ip(request),
    )
    return item


@router.post("/{item_id}/cancel", response_model=AppointmentPublic)
def cancel(
    item_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Appointment:
    item = _visible_appointment(db, item_id, user)
    if user.role != UserRole.PATIENT and not has_permission(user, ClinicalPermission.APPOINTMENT_MANAGE):
        record_audit_event(
            action=AuditAction.PERMISSION_DENIED,
            result=AuditResult.DENIED,
            clinic_id=user.clinic_id,
            actor_user_id=user.id,
            actor_email=user.email,
            ip_address=client_ip(request),
            user_agent=request.headers.get("user-agent"),
            metadata={"path": request.url.path, "required_permission": "appointment.manage"},
        )
        raise HTTPException(status_code=403, detail="Sem permissões para aceder a este recurso.")
    return _cancel_appointment(item, request, db, user)


def _cancel_appointment(item: Appointment, request: Request, db: Session, user: User) -> Appointment:
    validate_status_transition(item.status, AppointmentStatus.CANCELLED)
    item.status = AppointmentStatus.CANCELLED
    _notify_appointment_parties(
        db, item, user, "Consulta cancelada", "Uma consulta foi cancelada.", "appointment_cancelled"
    )
    db.commit()
    db.refresh(item)
    record_audit_event(
        action=AuditAction.APPOINTMENT_CANCELLED,
        result=AuditResult.SUCCESS,
        clinic_id=user.clinic_id,
        actor_user_id=user.id,
        actor_email=user.email,
        resource_type="appointment",
        resource_id=item.id,
        ip_address=client_ip(request),
    )
    return item


def _notify_appointment_parties(
    db: Session, item: Appointment, actor: User, title: str, message: str, kind: str
) -> None:
    recipients = {item.patient.user.id: item.patient.user, item.staff.user.id: item.staff.user}
    for recipient in recipients.values():
        if recipient.id != actor.id and recipient.is_active:
            create_notification(db, recipient, title, message, kind)
