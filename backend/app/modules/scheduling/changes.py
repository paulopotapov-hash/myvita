"""A patient cancels or reschedules their own appointment ("Cancelar" / "Remarcar").

Allowed only while the appointment is active and the clinic's deadline has not passed:
`cancellation_deadline_hours` before the start, counted in real hours (24 hours before
10:00 on the Sunday the clocks go forward is 09:00 on Saturday). After it the app shows
the clinic's phone instead.

Both run under the clinic scheduling lock, like every booking path:
- Cancel frees the slot at once and ends the care link the booking had created.
- Reschedule (direct types only; request types ask the clinic through a request)
  cancels the old appointment and books the new slot in ONE transaction: the old one is
  freed first, so the new time may overlap it; if the new slot was taken meanwhile, the
  whole change rolls back and the old appointment stays as it was (409).
"""

import uuid
from datetime import date, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import (
    Appointment,
    AppointmentStatus,
    AppointmentType,
    BookingMode,
    BookingSource,
    ClinicBookingSettings,
    Patient,
    Staff,
    User,
)
from app.modules.appointments.service import cancel_in_transaction, lock_clinic_schedule
from app.modules.notifications.events import NotificationEvent, notify
from app.modules.scheduling import clock, service
from app.modules.scheduling.availability import TZ, Slot, free_slots, patient_busy_intervals, slot_is_free
from app.modules.scheduling.booking import (
    OWN_OVERLAP_FOR_PATIENT,
    SLOT_TAKEN_FOR_PATIENT,
    AutoAssignment,
    booking_guard,
    ensure_care_assignment,
    release_care_assignment,
)
from app.modules.scheduling.eligibility import bookable_professionals, own_patient

ACTIVE = (AppointmentStatus.SCHEDULED, AppointmentStatus.CONFIRMED)
DEADLINE_PASSED = "Já não é possível alterar esta consulta na app. Contacta a clínica."
NOT_ACTIVE = "Esta consulta já não está ativa."
REQUEST_ONLY = "Esta consulta remarca-se por pedido à clínica."


def change_deadline(appointment: Appointment, settings: ClinicBookingSettings) -> datetime:
    return appointment.scheduled_at - timedelta(hours=settings.cancellation_deadline_hours)


def can_change(appointment: Appointment, settings: ClinicBookingSettings, at: datetime) -> bool:
    return appointment.status in ACTIVE and at < change_deadline(appointment, settings)


def _patient(db: Session, user: User) -> Patient:
    patient = own_patient(db, user)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Só pacientes alteram as suas consultas aqui.")
    return patient


def own_appointment(db: Session, patient: Patient, appointment_id: uuid.UUID) -> Appointment:
    """The patient's own appointment, or 404 (never reveals anyone else's)."""
    appointment = (
        db.query(Appointment)
        .filter(
            Appointment.id == appointment_id,
            Appointment.patient_id == patient.id,
            Appointment.clinic_id == patient.clinic_id,
        )
        .first()
    )
    if appointment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consulta não encontrada.")
    return appointment


def require_changeable(db: Session, appointment: Appointment) -> None:
    if appointment.status not in ACTIVE:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=NOT_ACTIVE)
    if not can_change(appointment, service.get_settings(db, appointment.clinic_id), clock.now()):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=DEADLINE_PASSED)


def cancel_by_patient(db: Session, user: User, appointment_id: uuid.UUID) -> tuple[Appointment, AutoAssignment | None]:
    patient = _patient(db, user)
    lock_clinic_schedule(db, patient.clinic_id)
    appointment = own_appointment(db, patient, appointment_id)
    require_changeable(db, appointment)
    ended = cancel_in_transaction(db, appointment, actor_user_id=user.id, notify_patient=False, notify_staff=True)
    db.commit()
    db.refresh(appointment)
    return appointment, ended


def _direct_type(db: Session, appointment: Appointment) -> AppointmentType:
    appointment_type = db.get(AppointmentType, appointment.appointment_type_id) if appointment.appointment_type_id else None
    if appointment_type is None or not appointment_type.active or appointment_type.booking_mode != BookingMode.DIRECT:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=REQUEST_ONLY)
    return appointment_type


def reschedule_slots(
    db: Session, user: User, appointment_id: uuid.UUID, day_from: date, day_to: date, *, same_professional: bool
) -> list[tuple[Slot, str]]:
    """Free slots to move this appointment to: with the same professional, or with any
    eligible one. The appointment's own time counts as free (it is the one moving)."""
    service.check_range(day_from, day_to)
    patient = _patient(db, user)
    appointment = own_appointment(db, patient, appointment_id)
    require_changeable(db, appointment)
    appointment_type = _direct_type(db, appointment)
    settings = service.get_settings(db, patient.clinic_id)
    today = clock.now().astimezone(TZ).date()
    day_from = max(day_from, today)
    day_to = min(day_to, today + timedelta(days=settings.booking_horizon_days))
    eligible = bookable_professionals(db, clinic_id=patient.clinic_id, appointment_type_id=appointment_type.id, patient=patient)
    names = {staff.id: name for staff, name, _known in eligible}
    staff_ids = [appointment.staff_id] if same_professional else list(names)
    staff_ids = [staff_id for staff_id in staff_ids if staff_id in names]
    found = free_slots(
        db,
        clinic_id=patient.clinic_id,
        appointment_type=appointment_type,
        staff_ids=staff_ids,
        day_from=day_from,
        day_to=day_to,
        ignore_appointment_id=appointment.id,
    )
    busy = patient_busy_intervals(db, patient.id, found, ignore_appointment_id=appointment.id)
    return [
        (slot, names[slot.staff_id])
        for slot in found
        if slot.starts_at != appointment.scheduled_at or slot.staff_id != appointment.staff_id
        if not any(start < slot.ends_at and end > slot.starts_at for start, end in busy)
    ]


def reschedule_by_patient(
    db: Session, user: User, appointment_id: uuid.UUID, *, starts_at: datetime, staff_id: uuid.UUID | None
) -> tuple[Appointment, Appointment, AutoAssignment | None, AutoAssignment | None]:
    """Returns (new appointment, old appointment, care link created, care link ended)."""
    patient = _patient(db, user)
    try:
        return _reschedule(db, user, patient, appointment_id, starts_at=starts_at, staff_id=staff_id)
    except HTTPException:
        db.rollback()  # the old appointment stays exactly as it was
        raise


def _reschedule(
    db: Session, user: User, patient: Patient, appointment_id: uuid.UUID, *, starts_at: datetime, staff_id: uuid.UUID | None
) -> tuple[Appointment, Appointment, AutoAssignment | None, AutoAssignment | None]:
    with booking_guard(db, patient_facing=True):
        lock_clinic_schedule(db, patient.clinic_id)
        old = own_appointment(db, patient, appointment_id)
        require_changeable(db, old)
        appointment_type = _direct_type(db, old)
        at = clock.now()
        horizon = service.get_settings(db, patient.clinic_id).booking_horizon_days
        if starts_at <= at or starts_at > at + timedelta(days=horizon + 1):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=SLOT_TAKEN_FOR_PATIENT)
        if starts_at == old.scheduled_at and staff_id in (None, old.staff_id):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Escolhe um horário diferente.")
        eligible = bookable_professionals(
            db, clinic_id=patient.clinic_id, appointment_type_id=appointment_type.id, patient=patient
        )
        candidates = [staff.id for staff, _name, _known in eligible]
        if staff_id is not None:
            if staff_id not in candidates:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profissional não disponível.")
            candidates = [staff_id]

        new, created, ended = book_replacement(
            db, user=user, patient=patient, old=old, appointment_type=appointment_type, candidates=candidates,
            starts_at=starts_at, booked_via=BookingSource.PATIENT, at=at,
        )
        db.commit()
    db.refresh(new)
    db.refresh(old)
    return new, old, created, ended


def book_replacement(
    db: Session,
    *,
    user: User,
    patient: Patient,
    old: Appointment,
    appointment_type: AppointmentType,
    candidates: list[uuid.UUID],
    starts_at: datetime,
    booked_via: BookingSource,
    at: datetime,
) -> tuple[Appointment, AutoAssignment | None, AutoAssignment | None]:
    """Move `old` to `starts_at` with the first candidate free then, inside the caller's
    transaction and clinic lock (a reschedule, or an accepted waiting-list offer). The old
    time is freed first (flushed), since the new slot may overlap it; a 409 leaves the
    caller to roll everything back. Returns (new appointment, care link created, ended)."""
    cancel_in_transaction(
        db, old, actor_user_id=user.id, notify_patient=False, notify_staff=False, release_link=False, offer_slot=False
    )
    chosen = next(
        (
            candidate
            for candidate in candidates
            if slot_is_free(
                db,
                clinic_id=patient.clinic_id,
                appointment_type=appointment_type,
                staff_id=candidate,
                starts_at=starts_at,
                now=at,
            )
        ),
        None,
    )
    if chosen is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=SLOT_TAKEN_FOR_PATIENT)
    ends_at = starts_at + timedelta(minutes=appointment_type.duration_minutes)
    overlapping = (
        db.query(Appointment.id)
        .filter(
            Appointment.patient_id == patient.id,
            Appointment.status.in_(ACTIVE),
            Appointment.scheduled_at < ends_at,
            Appointment.ends_at > starts_at,
        )
        .first()
    )
    if overlapping is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=OWN_OVERLAP_FOR_PATIENT)
    new = Appointment(
        clinic_id=patient.clinic_id,
        patient_id=patient.id,
        staff_id=chosen,
        scheduled_at=starts_at,
        duration_minutes=appointment_type.duration_minutes,
        appointment_type_id=appointment_type.id,
        booked_via=booked_via,
        status=AppointmentStatus.CONFIRMED,
        reason=old.reason,
        rescheduled_from_id=old.id,
    )
    db.add(new)
    db.flush()
    staff = db.get(Staff, chosen)
    assert staff is not None
    if chosen == old.staff_id:
        notify(db, NotificationEvent.APPOINTMENT_UPDATED, clinic_id=patient.clinic_id, recipient_user_id=staff.user_id)
    else:
        old_staff = db.get(Staff, old.staff_id)
        if old_staff is not None:
            notify(
                db,
                NotificationEvent.APPOINTMENT_CANCELLED_FOR_STAFF,
                clinic_id=patient.clinic_id,
                recipient_user_id=old_staff.user_id,
                dedupe_key=str(old.id),
            )
        notify(
            db,
            NotificationEvent.APPOINTMENT_ASSIGNED,
            clinic_id=patient.clinic_id,
            recipient_user_id=staff.user_id,
            dedupe_key=str(new.id),
        )
    from app.modules.scheduling import waitlist

    waitlist.offer_freed_slot(db, old)  # now that the new appointment holds its part of the time
    ended = release_care_assignment(db, appointment=old, patient_id=patient.id, staff_id=old.staff_id)
    created = ensure_care_assignment(
        db, clinic_id=patient.clinic_id, patient_id=patient.id, staff=staff, actor_user_id=user.id, appointment_id=new.id
    )
    return new, created, ended
