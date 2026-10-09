import uuid
from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.clinical_access import ClinicalAction, has_role_action, staff_profile
from app.models import (
    Appointment,
    AppointmentStatus,
    ClinicalCareAssignment,
    Notification,
    Patient,
    Staff,
    StaffRole,
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


def _add_staff_notification(db: Session, staff: Staff, *, title: str, message: str) -> None:
    db.add(
        Notification(
            clinic_id=staff.clinic_id,
            user_id=staff.user_id,
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
    _add_staff_notification(
        db,
        staff,
        title="Consulta atribuída",
        message="Foi atribuída uma consulta à sua agenda.",
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

    old_patient_id = appointment.patient_id
    old_staff_id = appointment.staff_id
    old_scheduled_at = appointment.scheduled_at
    old_status = appointment.status
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
    meaningful_change = any(
        (
            patient_id != old_patient_id,
            staff_id != old_staff_id,
            scheduled_at != old_scheduled_at,
            payload.status is not None and payload.status != old_status,
        )
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
    if meaningful_change:
        recipient_patients = {patient.id: patient}
        recipient_staff = {staff.id: staff}
        if old_patient_id != patient.id:
            old_patient = db.get(Patient, old_patient_id)
            if old_patient is not None and str(old_patient.clinic_id) == str(clinic_id):
                recipient_patients[old_patient.id] = old_patient
        if old_staff_id != staff.id:
            old_staff = db.get(Staff, old_staff_id)
            if old_staff is not None and str(old_staff.clinic_id) == str(clinic_id):
                recipient_staff[old_staff.id] = old_staff
        for patient_recipient in recipient_patients.values():
            _add_patient_notification(db, patient_recipient, title=title, message=message)
        for staff_recipient in recipient_staff.values():
            _add_staff_notification(db, staff_recipient, title=title, message=message)
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
    staff = db.get(Staff, appointment.staff_id)
    if staff is not None and str(staff.clinic_id) == str(clinic_id):
        _add_staff_notification(
            db,
            staff,
            title="Consulta cancelada",
            message="Uma consulta atribuída à sua agenda foi cancelada.",
        )
    db.commit()
    db.refresh(appointment)
    return appointment


def list_appointments_for_user(
    db: Session, user: User, *, offset: int = 0, limit: int = 50
) -> tuple[list[Appointment], int]:
    """
    Patients only ever see their own appointments. Clinic admins and
    administrative staff see every appointment within their own clinic;
    clinicians (doctor/nurse) only those of patients on their care team
    (active ClinicalCareAssignment). Never another clinic's, regardless of
    what they might try to pass in query params (there are deliberately no
    clinic_id/patient_id filters accepted from the client on this endpoint).
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
    if user.role == UserRole.STAFF:
        staff = staff_profile(db, user)
        if staff is None or not has_role_action(staff.staff_role, ClinicalAction.VIEW_APPOINTMENTS):
            return [], 0
        if staff.staff_role != StaffRole.ADMIN:
            assigned_patient_ids = db.query(ClinicalCareAssignment.patient_id).filter(
                ClinicalCareAssignment.clinic_id == user.clinic_id,
                ClinicalCareAssignment.staff_id == staff.id,
                ClinicalCareAssignment.active.is_(True),
            )
            query = query.filter(Appointment.patient_id.in_(assigned_patient_ids))
    total = query.count()
    rows = query.order_by(Appointment.scheduled_at, Appointment.id).offset(offset).limit(limit).all()
    return rows, total
