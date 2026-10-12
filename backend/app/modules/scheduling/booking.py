"""Shared booking primitives used by every path that creates or moves an appointment
(staff scheduling, patient self-booking, accepted requests, waitlist offers).

- `commit_booking`: the database exclusion constraints (migration 7d2e4b9a1c3f) are the
  final word on double booking, also under concurrent requests. A violation becomes a
  409 with a clear message; nothing is half-written.
- `ensure_care_assignment`: booking with a professional makes them part of the
  patient's care team (approved decision), in the same transaction as the appointment.
  An existing active assignment is never replaced or duplicated; non-clinical roles
  (administrative staff) are never assigned. The caller audits the returned assignment
  after the commit (audit runs in its own transaction, decision D9).
- `release_care_assignment`: the automatic link belongs to the appointment that created
  it. When that appointment is cancelled, or moved to another professional or patient,
  the link ends, unless another active appointment with the same professional remains:
  then that appointment becomes its origin. Links assigned by an admin (no origin) are
  never ended here.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Appointment, AppointmentStatus, ClinicalCareAssignment, Staff, StaffRole

STAFF_OVERLAP_CONSTRAINT = "ex_appointments_staff_no_overlap"
PATIENT_OVERLAP_CONSTRAINT = "ex_appointments_patient_no_overlap"
STAFF_TAKEN = "Este horário já não está disponível para este profissional."
PATIENT_TAKEN = "O paciente já tem uma consulta a essa hora."
# Wording for the patient's own booking screens.
SLOT_TAKEN_FOR_PATIENT = "Este horário já não está disponível. Escolhe outro."
OWN_OVERLAP_FOR_PATIENT = "Já tens uma consulta a essa hora."
CLINICAL_ROLES = frozenset({StaffRole.DOCTOR, StaffRole.NURSE, StaffRole.PHYSIOTHERAPIST})
ACTIVE_STATUSES = (AppointmentStatus.SCHEDULED, AppointmentStatus.CONFIRMED)


@dataclass(frozen=True)
class AutoAssignment:
    assignment_id: uuid.UUID
    patient_id: uuid.UUID
    staff_id: uuid.UUID


def overlap_message(exc: IntegrityError, *, patient_facing: bool = False) -> str | None:
    """The 409 message for an exclusion violation, or None for any other integrity error."""
    diag = getattr(exc.orig, "diag", None)
    constraint = getattr(diag, "constraint_name", None)
    if constraint == STAFF_OVERLAP_CONSTRAINT:
        return SLOT_TAKEN_FOR_PATIENT if patient_facing else STAFF_TAKEN
    if constraint == PATIENT_OVERLAP_CONSTRAINT:
        return OWN_OVERLAP_FOR_PATIENT if patient_facing else PATIENT_TAKEN
    return None


@contextmanager
def booking_guard(db: Session, *, patient_facing: bool = False) -> Iterator[None]:
    """Wrap a whole booking change: an exclusion violation can surface at any flush (an
    autoflush before a query, the explicit flush, or the commit). It becomes a 409 and the
    transaction is rolled back; any other integrity error propagates unchanged."""
    try:
        yield
    except IntegrityError as exc:
        db.rollback()
        message = overlap_message(exc, patient_facing=patient_facing)
        if message is None:
            raise
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message) from exc


def commit_booking(db: Session) -> None:
    with booking_guard(db):
        db.commit()


def ensure_care_assignment(
    db: Session,
    *,
    clinic_id: uuid.UUID,
    patient_id: uuid.UUID,
    staff: Staff,
    actor_user_id: uuid.UUID,
    appointment_id: uuid.UUID,
) -> AutoAssignment | None:
    """Add the professional to the patient's care team if they are not on it yet."""
    if staff.staff_role not in CLINICAL_ROLES or str(staff.clinic_id) != str(clinic_id):
        return None
    existing = (
        db.query(ClinicalCareAssignment.id)
        .filter(
            ClinicalCareAssignment.clinic_id == clinic_id,
            ClinicalCareAssignment.patient_id == patient_id,
            ClinicalCareAssignment.staff_id == staff.id,
            ClinicalCareAssignment.active.is_(True),
        )
        .first()
    )
    if existing is not None:
        return None
    assignment = ClinicalCareAssignment(
        clinic_id=clinic_id,
        patient_id=patient_id,
        staff_id=staff.id,
        assigned_by_user_id=actor_user_id,
        origin_appointment_id=appointment_id,
    )
    savepoint = db.begin_nested()
    try:
        db.add(assignment)
        db.flush()
    except IntegrityError:
        # A concurrent booking assigned them first: keep that one.
        savepoint.rollback()
        return None
    savepoint.commit()
    return AutoAssignment(assignment_id=assignment.id, patient_id=patient_id, staff_id=staff.id)


def release_care_assignment(
    db: Session, *, appointment: Appointment, patient_id: uuid.UUID, staff_id: uuid.UUID
) -> AutoAssignment | None:
    """The appointment no longer ties this patient to this professional (cancelled, or moved
    to someone else): end the link it created. Runs in the caller's transaction, under the
    clinic scheduling lock; returns the ended link for the caller to audit after the commit."""
    assignment = (
        db.query(ClinicalCareAssignment)
        .filter(
            ClinicalCareAssignment.clinic_id == appointment.clinic_id,
            ClinicalCareAssignment.patient_id == patient_id,
            ClinicalCareAssignment.staff_id == staff_id,
            ClinicalCareAssignment.origin_appointment_id == appointment.id,
            ClinicalCareAssignment.active.is_(True),
        )
        .with_for_update()
        .first()
    )
    if assignment is None:
        return None
    remaining = (
        db.query(Appointment.id)
        .filter(
            Appointment.clinic_id == appointment.clinic_id,
            Appointment.patient_id == patient_id,
            Appointment.staff_id == staff_id,
            Appointment.id != appointment.id,
            Appointment.status.in_(ACTIVE_STATUSES),
        )
        .order_by(Appointment.scheduled_at, Appointment.id)
        .first()
    )
    if remaining is not None:
        assignment.origin_appointment_id = remaining.id
        return None
    assignment.active = False
    assignment.ended_at = datetime.now(UTC)
    return AutoAssignment(assignment_id=assignment.id, patient_id=patient_id, staff_id=staff_id)
