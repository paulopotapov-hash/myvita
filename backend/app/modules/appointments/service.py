import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.clinical_access import ClinicalAction, has_role_action, staff_profile
from app.models import (
    Appointment,
    AppointmentStatus,
    BookingSource,
    ClinicalCareAssignment,
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
from app.modules.notifications.events import NotificationEvent, notify
from app.modules.scheduling.booking import (
    PATIENT_TAKEN,
    AutoAssignment,
    booking_guard,
    commit_booking,
    ensure_care_assignment,
    release_care_assignment,
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


# Public name for the other booking paths (patient self-booking, requests, waitlist).
def lock_clinic_schedule(db: Session, clinic_id: object) -> None:
    _lock_clinic_schedule(db, str(clinic_id))


def _add_patient_notification(
    db: Session, patient: Patient, *, event: NotificationEvent, dedupe_key: str | None = None
) -> None:
    notify(db, event, clinic_id=patient.clinic_id, recipient_user_id=patient.user_id, dedupe_key=dedupe_key)


def _add_staff_notification(
    db: Session, staff: Staff, *, event: NotificationEvent, dedupe_key: str | None = None
) -> None:
    notify(db, event, clinic_id=staff.clinic_id, recipient_user_id=staff.user_id, dedupe_key=dedupe_key)


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


def _ensure_patient_free(
    db: Session,
    *,
    patient_id: uuid.UUID,
    scheduled_at: datetime,
    duration_minutes: int,
    exclude_id: uuid.UUID | None = None,
) -> None:
    """The same patient never has two active appointments at the same time (also enforced
    by the database exclusion constraint; this gives the clearer message first)."""
    end_at = scheduled_at + timedelta(minutes=duration_minutes)
    query = db.query(Appointment).filter(
        Appointment.patient_id == patient_id,
        Appointment.status.in_([AppointmentStatus.SCHEDULED, AppointmentStatus.CONFIRMED]),
        Appointment.scheduled_at < end_at,
        Appointment.ends_at > scheduled_at,
    )
    if exclude_id is not None:
        query = query.filter(Appointment.id != exclude_id)
    if query.first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PATIENT_TAKEN)


def create_appointment(
    db: Session, clinic_id: str, payload: AppointmentCreateRequest, actor_user_id: uuid.UUID
) -> tuple[Appointment, AutoAssignment | None]:
    with booking_guard(db):
        appointment, assignment, _ended = _create_appointment(db, clinic_id, payload, actor_user_id)
        return appointment, assignment


def create_appointment_from_request(
    db: Session,
    clinic_id: str,
    payload: AppointmentCreateRequest,
    actor_user_id: uuid.UUID,
    *,
    appointment_type_id: uuid.UUID | None,
    replaces: Appointment | None,
    before_commit: Callable[[Appointment], None],
) -> tuple[Appointment, AutoAssignment | None, AutoAssignment | None]:
    """An accepted request: the appointment is typed, booked via "request", and, for a
    reschedule request, replaces the patient's appointment (cancelled in the same
    transaction). `before_commit` links the request to the new appointment, so both are
    committed together. Returns the appointment and the care links created and ended."""
    with booking_guard(db):
        return _create_appointment(
            db,
            clinic_id,
            payload,
            actor_user_id,
            appointment_type_id=appointment_type_id,
            booked_via=BookingSource.REQUEST,
            replaces=replaces,
            before_commit=before_commit,
        )


def cancel_in_transaction(
    db: Session,
    appointment: Appointment,
    *,
    actor_user_id: uuid.UUID,
    notify_patient: bool,
    notify_staff: bool,
    release_link: bool = True,
    offer_slot: bool = True,
) -> AutoAssignment | None:
    """Cancel an active appointment inside the caller's transaction (under the clinic
    lock): record who and when, notify, free the slot (flushed, so the caller's next
    availability or overlap check already sees it) and end the care link it created.
    Returns that link, for the caller to audit after the commit. A reschedule passes
    `release_link=False` and releases it once the new appointment exists, so a link to
    the same professional moves to the new appointment instead of ending; it also passes
    `offer_slot=False` and offers the old slot to the waiting list once the new appointment
    exists (the new one may take part of it)."""
    appointment.status = AppointmentStatus.CANCELLED
    appointment.cancelled_at = datetime.now(UTC)
    appointment.cancelled_by_user_id = actor_user_id
    if notify_patient:
        patient = db.get(Patient, appointment.patient_id)
        if patient is not None:
            _add_patient_notification(
                db, patient, event=NotificationEvent.APPOINTMENT_CANCELLED, dedupe_key=str(appointment.id)
            )
    if notify_staff:
        staff = db.get(Staff, appointment.staff_id)
        if staff is not None and str(staff.clinic_id) == str(appointment.clinic_id):
            _add_staff_notification(
                db, staff, event=NotificationEvent.APPOINTMENT_CANCELLED_FOR_STAFF, dedupe_key=str(appointment.id)
            )
    db.flush()
    # The waiting list: this appointment's own entry ends, and its slot is offered.
    from app.modules.scheduling import waitlist

    waitlist.close_for_appointment(db, appointment.id)
    if offer_slot:
        waitlist.offer_freed_slot(db, appointment)
    if not release_link:
        return None
    return release_care_assignment(
        db, appointment=appointment, patient_id=appointment.patient_id, staff_id=appointment.staff_id
    )


def _create_appointment(
    db: Session,
    clinic_id: str,
    payload: AppointmentCreateRequest,
    actor_user_id: uuid.UUID,
    *,
    appointment_type_id: uuid.UUID | None = None,
    booked_via: BookingSource = BookingSource.STAFF,
    replaces: Appointment | None = None,
    before_commit: Callable[[Appointment], None] | None = None,
) -> tuple[Appointment, AutoAssignment | None, AutoAssignment | None]:
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

    if replaces is not None:
        # Freed first: the new time may overlap the old one (same patient, maybe same professional).
        db.refresh(replaces)
        if replaces.status in (AppointmentStatus.SCHEDULED, AppointmentStatus.CONFIRMED):
            cancel_in_transaction(
                db,
                replaces,
                actor_user_id=actor_user_id,
                notify_patient=False,
                notify_staff=replaces.staff_id != staff.id,
                release_link=False,
                offer_slot=False,
            )
        else:
            replaces = None  # cancelled or finished meanwhile: the new appointment simply stands alone

    _ensure_no_conflict(
        db,
        clinic_id=clinic_id,
        staff_id=staff.id,
        scheduled_at=payload.scheduled_at,
        duration_minutes=payload.duration_minutes,
    )
    _ensure_patient_free(
        db, patient_id=patient.id, scheduled_at=payload.scheduled_at, duration_minutes=payload.duration_minutes
    )

    appointment = Appointment(
        clinic_id=clinic_id,
        patient_id=patient.id,
        staff_id=staff.id,
        scheduled_at=payload.scheduled_at,
        duration_minutes=payload.duration_minutes,
        reason=payload.reason,
        appointment_type_id=appointment_type_id,
        booked_via=booked_via,
        rescheduled_from_id=replaces.id if replaces is not None else None,
    )
    db.add(appointment)
    db.flush()
    _add_patient_notification(
        db, patient, event=NotificationEvent.APPOINTMENT_CREATED, dedupe_key=str(appointment.id)
    )
    _add_staff_notification(db, staff, event=NotificationEvent.APPOINTMENT_ASSIGNED, dedupe_key=str(appointment.id))
    ended = None
    if replaces is not None:
        from app.modules.scheduling import waitlist

        waitlist.offer_freed_slot(db, replaces)
        # The old appointment's link: moves to this one (same professional) or ends.
        ended = release_care_assignment(db, appointment=replaces, patient_id=replaces.patient_id, staff_id=replaces.staff_id)
    assignment = ensure_care_assignment(
        db,
        clinic_id=patient.clinic_id,
        patient_id=patient.id,
        staff=staff,
        actor_user_id=actor_user_id,
        appointment_id=appointment.id,
    )
    if before_commit is not None:
        before_commit(appointment)
    commit_booking(db)
    db.refresh(appointment)
    return appointment, assignment, ended


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
    db: Session, appointment_id: uuid.UUID, clinic_id: str, payload: AppointmentUpdateRequest, actor_user_id: uuid.UUID
) -> tuple[Appointment, AutoAssignment | None, AutoAssignment | None]:
    """Returns the appointment, the care assignment it created (if any) and the one it
    ended (if moved away from the professional or patient whose link it had created)."""
    with booking_guard(db):
        return _update_appointment(db, appointment_id, clinic_id, payload, actor_user_id)


def _update_appointment(
    db: Session, appointment_id: uuid.UUID, clinic_id: str, payload: AppointmentUpdateRequest, actor_user_id: uuid.UUID
) -> tuple[Appointment, AutoAssignment | None, AutoAssignment | None]:
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
    _ensure_patient_free(
        db, patient_id=patient_id, scheduled_at=scheduled_at, duration_minutes=duration, exclude_id=appointment.id
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
    moved = staff_id != old_staff_id or scheduled_at != old_scheduled_at or patient_id != old_patient_id
    if moved or appointment.status in (AppointmentStatus.COMPLETED, AppointmentStatus.NO_SHOW):
        # The waiting list: an entry was for this professional and time; a moved slot is offered.
        from app.modules.scheduling import waitlist

        db.flush()
        waitlist.close_for_appointment(db, appointment.id)
        if moved and old_status in (AppointmentStatus.SCHEDULED, AppointmentStatus.CONFIRMED):
            waitlist.offer_freed_slot(
                db,
                waitlist.FreedSlot(
                    clinic_id=appointment.clinic_id, patient_id=old_patient_id, staff_id=old_staff_id, scheduled_at=old_scheduled_at
                ),
            )
    status_events = {
        AppointmentStatus.CONFIRMED: NotificationEvent.APPOINTMENT_CONFIRMED,
        AppointmentStatus.COMPLETED: NotificationEvent.APPOINTMENT_COMPLETED,
        AppointmentStatus.NO_SHOW: NotificationEvent.APPOINTMENT_NO_SHOW,
    }
    event = status_events.get(appointment.status, NotificationEvent.APPOINTMENT_UPDATED)
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
        # Repeated edits are separate events: no dedupe key (the status ones
        # cannot repeat, the transition table only moves forward).
        for patient_recipient in recipient_patients.values():
            _add_patient_notification(db, patient_recipient, event=event)
        for staff_recipient in recipient_staff.values():
            _add_staff_notification(db, staff_recipient, event=event)
    assignment = ended = None
    if staff_id != old_staff_id or patient_id != old_patient_id:
        db.flush()
        ended = release_care_assignment(db, appointment=appointment, patient_id=old_patient_id, staff_id=old_staff_id)
        assignment = ensure_care_assignment(
            db,
            clinic_id=patient.clinic_id,
            patient_id=patient.id,
            staff=staff,
            actor_user_id=actor_user_id,
            appointment_id=appointment.id,
        )
    commit_booking(db)
    db.refresh(appointment)
    return appointment, assignment, ended


def cancel_appointment(
    db: Session, appointment_id: uuid.UUID, clinic_id: str, actor_user_id: uuid.UUID
) -> tuple[Appointment, AutoAssignment | None]:
    """Returns the cancelled appointment and the care assignment it had created, if that
    link ended with it (for the caller to audit)."""
    _lock_clinic_schedule(db, clinic_id)
    appointment = get_appointment_for_clinic(db, appointment_id, clinic_id)
    if appointment.status == AppointmentStatus.CANCELLED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Consulta já cancelada.")
    if appointment.status in {AppointmentStatus.COMPLETED, AppointmentStatus.NO_SHOW}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Consulta já finalizada.")
    if db.get(Patient, appointment.patient_id) is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Paciente da consulta indisponível.")
    ended = cancel_in_transaction(db, appointment, actor_user_id=actor_user_id, notify_patient=True, notify_staff=True)
    db.commit()
    db.refresh(appointment)
    return appointment, ended


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
