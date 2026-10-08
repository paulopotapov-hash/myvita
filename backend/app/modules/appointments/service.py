import uuid
from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import (
    Appointment,
    AppointmentStatus,
    Notification,
    Patient,
    Staff,
    User,
    UserRole,
)
from app.modules.appointments.schemas import (
    AppointmentCreateRequest,
    AppointmentUpdateRequest,
)

_VALID_STATUS_TRANSITIONS: dict[AppointmentStatus, set[AppointmentStatus]] = {
    AppointmentStatus.SCHEDULED: {AppointmentStatus.CONFIRMED},
    AppointmentStatus.CONFIRMED: {AppointmentStatus.COMPLETED, AppointmentStatus.NO_SHOW},
}


def _lock_clinic_schedule(db: Session, clinic_id: str) -> None:
    """Serialize schedule mutations for one clinic until transaction end.

    PostgreSQL advisory transaction locks close the check-then-insert race
    without requiring a global lock or an extension. Every create/update/
    cancel path takes the same clinic-scoped lock before checking conflicts.
    """
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": f"myvita:appointment-schedule:{clinic_id}"},
    )


def _add_patient_notification(db: Session, patient: Patient, *, title: str, message: str) -> None:
    db.add(
        Notification(
            clinic_id=patient.clinic_id,
            user_id=patient.user_id,
            title=title,
            message=message,
        )
    )


def _ensure_no_conflict(
    db: Session,
    *,
    clinic_id: str,
    staff_id: uuid.UUID,
    scheduled_at: datetime,
    duration_minutes: int,
    exclude_id: uuid.UUID | None = None,
) -> None:
    end_at = scheduled_at + timedelta(minutes=duration_minutes)
    query = db.query(Appointment).filter(
        Appointment.clinic_id == clinic_id,
        Appointment.staff_id == staff_id,
        Appointment.status.in_([AppointmentStatus.SCHEDULED, AppointmentStatus.CONFIRMED]),
        Appointment.scheduled_at < end_at,
    )
    if exclude_id is not None:
        query = query.filter(Appointment.id != exclude_id)
    for existing in query.all():
        existing_end = existing.scheduled_at + timedelta(minutes=existing.duration_minutes)
        if existing_end > scheduled_at:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Já existe uma consulta sobreposta para este profissional.",
            )


def create_appointment(db: Session, clinic_id: str, payload: AppointmentCreateRequest) -> Appointment:
    """
    clinic_id comes from the authenticated staff member's session, never
    from the request body. We still re-verify that both the patient and
    the staff member actually belong to THIS clinic before creating the
    appointment — otherwise a staff member could pass another clinic's
    patient_id/staff_id and create a cross-tenant appointment (IDOR).
    """
    _lock_clinic_schedule(db, clinic_id)
    patient = db.get(Patient, payload.patient_id)
    if patient is None or str(patient.clinic_id) != str(clinic_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Paciente não encontrado nesta clínica.",
        )

    staff = db.get(Staff, payload.staff_id)
    if staff is None or str(staff.clinic_id) != str(clinic_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profissional não encontrado nesta clínica.",
        )

    _ensure_no_conflict(
        db,
        clinic_id=clinic_id,
        staff_id=staff.id,
        scheduled_at=payload.scheduled_at,
        duration_minutes=payload.duration_minutes,
    )

    appointment = Appointment(
        clinic_id=clinic_id,
        patient_id=patient.id,
        staff_id=staff.id,
        scheduled_at=payload.scheduled_at,
        duration_minutes=payload.duration_minutes,
        reason=payload.reason,
    )
    db.add(appointment)
    _add_patient_notification(
        db,
        patient,
        title="Consulta criada",
        message="Foi criada uma consulta na sua agenda.",
    )
    db.commit()
    db.refresh(appointment)
    return appointment


def get_appointment_for_clinic(db: Session, appointment_id: uuid.UUID, clinic_id: str) -> Appointment:
    appointment = (
        db.query(Appointment)
        .filter(Appointment.id == appointment_id, Appointment.clinic_id == clinic_id)
        .first()
    )
    if appointment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consulta não encontrada.")
    return appointment


def update_appointment(
    db: Session, appointment_id: uuid.UUID, clinic_id: str, payload: AppointmentUpdateRequest
) -> Appointment:
    _lock_clinic_schedule(db, clinic_id)
    appointment = get_appointment_for_clinic(db, appointment_id, clinic_id)
    if appointment.status in {
        AppointmentStatus.CANCELLED,
        AppointmentStatus.COMPLETED,
        AppointmentStatus.NO_SHOW,
    }:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Consulta já finalizada.")

    if payload.status is not None and payload.status != appointment.status:
        allowed = _VALID_STATUS_TRANSITIONS.get(appointment.status, set())
        if payload.status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Transição de {appointment.status.value} para {payload.status.value} não permitida.",
            )

    patient_id = payload.patient_id or appointment.patient_id
    staff_id = payload.staff_id or appointment.staff_id
    patient = db.get(Patient, patient_id)
    staff = db.get(Staff, staff_id)
    if patient is None or str(patient.clinic_id) != str(clinic_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Paciente não encontrado nesta clínica."
        )
    if staff is None or str(staff.clinic_id) != str(clinic_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Profissional não encontrado nesta clínica."
        )

    scheduled_at = payload.scheduled_at or appointment.scheduled_at
    duration = payload.duration_minutes or appointment.duration_minutes
    _ensure_no_conflict(
        db,
        clinic_id=clinic_id,
        staff_id=staff_id,
        scheduled_at=scheduled_at,
        duration_minutes=duration,
        exclude_id=appointment.id,
    )
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(appointment, field, value)
    status_messages = {
        AppointmentStatus.CONFIRMED: ("Consulta confirmada", "Uma consulta da sua agenda foi confirmada."),
        AppointmentStatus.COMPLETED: ("Consulta concluída", "Uma consulta da sua agenda foi concluída."),
        AppointmentStatus.NO_SHOW: (
            "Falta registada",
            "Foi registada uma falta numa consulta da sua agenda.",
        ),
    }
    title, message = status_messages.get(
        appointment.status,
        ("Consulta atualizada", "Uma consulta da sua agenda foi atualizada."),
    )
    _add_patient_notification(db, patient, title=title, message=message)
    db.commit()
    db.refresh(appointment)
    return appointment


def cancel_appointment(db: Session, appointment_id: uuid.UUID, clinic_id: str) -> Appointment:
    _lock_clinic_schedule(db, clinic_id)
    appointment = get_appointment_for_clinic(db, appointment_id, clinic_id)
    if appointment.status == AppointmentStatus.CANCELLED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Consulta já cancelada.")
    if appointment.status in {AppointmentStatus.COMPLETED, AppointmentStatus.NO_SHOW}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Consulta já finalizada.")
    appointment.status = AppointmentStatus.CANCELLED
    patient = db.get(Patient, appointment.patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Paciente da consulta indisponível.")
    _add_patient_notification(
        db,
        patient,
        title="Consulta cancelada",
        message="Uma consulta da sua agenda foi cancelada.",
    )
    db.commit()
    db.refresh(appointment)
    return appointment


def list_appointments_for_user(
    db: Session, user: User, *, offset: int = 0, limit: int = 50
) -> tuple[list[Appointment], int]:
    """
    Patients only ever see their own appointments. Staff/clinic_admin see
    every appointment within their own clinic — never another clinic's,
    regardless of what they might try to pass in query params (there are
    deliberately no clinic_id/patient_id filters accepted from the client
    on this endpoint).
    """
    if user.role == UserRole.PATIENT:
        patient = db.query(Patient).filter(Patient.user_id == user.id).first()
        if patient is None:
            return [], 0
        query = db.query(Appointment).filter(Appointment.patient_id == patient.id)
        total = query.count()
        rows = query.order_by(Appointment.scheduled_at, Appointment.id).offset(offset).limit(limit).all()
        return rows, total

    # STAFF / CLINIC_ADMIN
    query = db.query(Appointment).filter(Appointment.clinic_id == user.clinic_id)
    total = query.count()
    rows = query.order_by(Appointment.scheduled_at, Appointment.id).offset(offset).limit(limit).all()
    return rows, total
