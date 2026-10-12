"""A patient's own booking ("Marcação direta"): the server re-checks everything.

Under the clinic's scheduling lock it verifies the type is bookable directly, the time is
in the future and within the clinic's horizon, the professional is eligible for this
patient (new-patient rule) and the slot is still one of their free slots; with
"Qualquer disponível" it takes the first eligible professional (known ones first) who is
free at that time. The appointment is created confirmed, the professional joins the care
team, and the exclusion constraints remain the final guard: if the slot was taken in the
meantime the answer is 409 "Este horário já não está disponível. Escolhe outro."
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Appointment, AppointmentStatus, BookingMode, BookingSource, Specialty, Staff, User
from app.modules.appointments.service import lock_clinic_schedule
from app.modules.notifications.events import NotificationEvent, notify
from app.modules.scheduling import service
from app.modules.scheduling.availability import slot_is_free
from app.modules.scheduling.booking import (
    OWN_OVERLAP_FOR_PATIENT,
    SLOT_TAKEN_FOR_PATIENT,
    AutoAssignment,
    booking_guard,
    ensure_care_assignment,
)
from app.modules.scheduling.eligibility import bookable_professionals, own_patient
from app.modules.scheduling.schemas import BookingIn

ACTIVE = (AppointmentStatus.SCHEDULED, AppointmentStatus.CONFIRMED)


def _conflict(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)


def book_for_patient(db: Session, user: User, payload: BookingIn) -> tuple[Appointment, AutoAssignment | None]:
    patient = own_patient(db, user)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Só pacientes marcam consultas aqui.")
    appointment_type = service.get_type(db, payload.appointment_type_id, patient.clinic_id, active_only=True)
    specialty = db.get(Specialty, appointment_type.specialty_id)
    if specialty is None or not specialty.active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Não encontrado.")
    if appointment_type.booking_mode != BookingMode.DIRECT:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Este tipo de consulta só se marca por pedido."
        )
    now = datetime.now(UTC)
    horizon = service.get_settings(db, patient.clinic_id).booking_horizon_days
    if payload.starts_at <= now or payload.starts_at > now + timedelta(days=horizon + 1):
        raise _conflict(SLOT_TAKEN_FOR_PATIENT)

    eligible = bookable_professionals(
        db, clinic_id=patient.clinic_id, appointment_type_id=appointment_type.id, patient=patient
    )
    candidates = [staff.id for staff, _name, _known in eligible]
    if payload.staff_id is not None:
        if payload.staff_id not in candidates:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profissional não disponível.")
        candidates = [payload.staff_id]

    with booking_guard(db, patient_facing=True):
        lock_clinic_schedule(db, patient.clinic_id)
        chosen = next(
            (
                staff_id
                for staff_id in candidates
                if slot_is_free(
                    db,
                    clinic_id=patient.clinic_id,
                    appointment_type=appointment_type,
                    staff_id=staff_id,
                    starts_at=payload.starts_at,
                    now=now,
                )
            ),
            None,
        )
        if chosen is None:
            raise _conflict(SLOT_TAKEN_FOR_PATIENT)
        ends_at = payload.starts_at + timedelta(minutes=appointment_type.duration_minutes)
        overlapping = (
            db.query(Appointment.id)
            .filter(
                Appointment.patient_id == patient.id,
                Appointment.status.in_(ACTIVE),
                Appointment.scheduled_at < ends_at,
                Appointment.ends_at > payload.starts_at,
            )
            .first()
        )
        if overlapping is not None:
            raise _conflict(OWN_OVERLAP_FOR_PATIENT)
        appointment = Appointment(
            clinic_id=patient.clinic_id,
            patient_id=patient.id,
            staff_id=chosen,
            scheduled_at=payload.starts_at,
            duration_minutes=appointment_type.duration_minutes,
            appointment_type_id=appointment_type.id,
            booked_via=BookingSource.PATIENT,
            status=AppointmentStatus.CONFIRMED,  # "Marcação direta": confirmed at once
            reason=payload.reason,
        )
        db.add(appointment)
        db.flush()
        staff = db.get(Staff, chosen)
        assert staff is not None
        notify(
            db,
            NotificationEvent.APPOINTMENT_ASSIGNED,
            clinic_id=patient.clinic_id,
            recipient_user_id=staff.user_id,
            dedupe_key=str(appointment.id),
        )
        assignment = ensure_care_assignment(
            db,
            clinic_id=patient.clinic_id,
            patient_id=patient.id,
            staff=staff,
            actor_user_id=user.id,
            appointment_id=appointment.id,
        )
        db.commit()
    db.refresh(appointment)
    return appointment, assignment


def bookable_for_patient(db: Session, user: User, type_id: uuid.UUID) -> list[tuple[Staff, str, bool]]:
    patient = own_patient(db, user)
    appointment_type = service.get_type(db, type_id, user.clinic_id, active_only=patient is not None)
    return bookable_professionals(db, clinic_id=user.clinic_id, appointment_type_id=appointment_type.id, patient=patient)
