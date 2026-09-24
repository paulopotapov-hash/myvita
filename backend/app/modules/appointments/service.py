import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Appointment, AppointmentStatus, Patient, Staff, User, UserRole
from app.modules.appointments.schemas import AppointmentCreateRequest
from app.modules.clinical.service import create_notification


def create_appointment(db: Session, clinic_id: str, payload: AppointmentCreateRequest) -> Appointment:
    """
    clinic_id comes from the authenticated staff member's session, never
    from the request body. We still re-verify that both the patient and
    the staff member actually belong to THIS clinic before creating the
    appointment — otherwise a staff member could pass another clinic's
    patient_id/staff_id and create a cross-tenant appointment (IDOR).
    """
    patient = db.get(Patient, payload.patient_id)
    if patient is None or str(patient.clinic_id) != str(clinic_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Paciente não encontrado nesta clínica.",
        )
    if not patient.user.is_active:
        raise HTTPException(status_code=409, detail="Paciente inativo.")

    staff = db.get(Staff, payload.staff_id)
    if staff is None or str(staff.clinic_id) != str(clinic_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profissional não encontrado nesta clínica.",
        )
    if not staff.user.is_active:
        raise HTTPException(status_code=409, detail="Profissional inativo.")

    validate_slot(db, clinic_id, payload.staff_id, payload.scheduled_at, payload.duration_minutes)
    appointment = Appointment(
        clinic_id=clinic_id,
        patient_id=patient.id,
        staff_id=staff.id,
        scheduled_at=payload.scheduled_at,
        duration_minutes=payload.duration_minutes,
        reason=payload.reason,
    )
    db.add(appointment)
    db.flush()
    create_notification(
        db, patient.user, "Consulta marcada", "Foi marcada uma nova consulta.", "appointment_created"
    )
    create_notification(
        db, staff.user, "Consulta marcada", "Foi marcada uma nova consulta.", "appointment_created"
    )
    db.commit()
    db.refresh(appointment)
    return appointment


ALLOWED_STATUS_TRANSITIONS: dict[AppointmentStatus, frozenset[AppointmentStatus]] = {
    AppointmentStatus.SCHEDULED: frozenset(
        {AppointmentStatus.CONFIRMED, AppointmentStatus.CANCELLED, AppointmentStatus.NO_SHOW}
    ),
    AppointmentStatus.CONFIRMED: frozenset(
        {AppointmentStatus.COMPLETED, AppointmentStatus.CANCELLED, AppointmentStatus.NO_SHOW}
    ),
    AppointmentStatus.COMPLETED: frozenset(),
    AppointmentStatus.CANCELLED: frozenset(),
    AppointmentStatus.NO_SHOW: frozenset(),
}


def validate_status_transition(current: AppointmentStatus, target: AppointmentStatus) -> None:
    if target not in ALLOWED_STATUS_TRANSITIONS[current]:
        raise HTTPException(status_code=409, detail="Transição de estado inválida.")


def list_appointments_for_user(
    db: Session,
    user: User,
    limit: int = 50,
    offset: int = 0,
    *,
    patient_id: uuid.UUID | None = None,
    staff_id: uuid.UUID | None = None,
    appointment_status: AppointmentStatus | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> list[Appointment]:
    """
    Patients only ever see their own appointments. Staff/clinic_admin see
    every appointment within their own clinic — never another clinic's,
    even when optional filters are supplied. Every filter narrows the
    server-side authorization scope; none can broaden it.
    """
    query = db.query(Appointment)
    if user.role == UserRole.PATIENT:
        patient = db.query(Patient).filter(Patient.user_id == user.id).first()
        if patient is None:
            return []
        query = query.filter(Appointment.patient_id == patient.id)
    else:
        query = query.filter(Appointment.clinic_id == user.clinic_id)

    if patient_id is not None:
        query = query.filter(Appointment.patient_id == patient_id)
    if staff_id is not None:
        query = query.filter(Appointment.staff_id == staff_id)
    if appointment_status is not None:
        query = query.filter(Appointment.status == appointment_status)
    if start_date is not None:
        query = query.filter(Appointment.scheduled_at >= start_date)
    if end_date is not None:
        query = query.filter(Appointment.scheduled_at <= end_date)
    return query.order_by(Appointment.scheduled_at).offset(offset).limit(limit).all()


def validate_slot(
    db: Session,
    clinic_id: str,
    staff_id: uuid.UUID,
    start: datetime,
    duration: int,
    exclude_id: uuid.UUID | None = None,
) -> None:
    if start.tzinfo is None or start.utcoffset() is None:
        raise HTTPException(status_code=422, detail="A data deve incluir timezone.")
    if start <= datetime.now(UTC):
        raise HTTPException(status_code=422, detail="A consulta deve ser no futuro.")
    end = start + timedelta(minutes=duration)
    # Serialize booking decisions for one staff member across concurrent requests.
    db.query(Staff).filter(Staff.id == staff_id, Staff.clinic_id == clinic_id).with_for_update().one()
    existing = (
        db.query(Appointment)
        .filter(
            Appointment.clinic_id == clinic_id,
            Appointment.staff_id == staff_id,
            Appointment.status.notin_([AppointmentStatus.CANCELLED, AppointmentStatus.NO_SHOW]),
            Appointment.scheduled_at < end,
        )
        .all()
    )
    if any(
        a.id != exclude_id and a.scheduled_at + timedelta(minutes=a.duration_minutes) > start
        for a in existing
    ):
        raise HTTPException(status_code=409, detail="O profissional já tem uma consulta nesse horário.")
