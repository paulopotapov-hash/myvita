"""Which professionals a patient may book with (and in which order)."""

import uuid

from sqlalchemy.orm import Session

from app.models import Appointment, AppointmentStatus, Patient, ScheduleRule, ScheduleRuleType, Staff, User

# "Médicos com quem já teve consulta": any appointment that was not cancelled.
PAST_RELATION = (
    AppointmentStatus.SCHEDULED,
    AppointmentStatus.CONFIRMED,
    AppointmentStatus.COMPLETED,
    AppointmentStatus.NO_SHOW,
)


def own_patient(db: Session, user: User) -> Patient | None:
    return db.query(Patient).filter(Patient.user_id == user.id, Patient.clinic_id == user.clinic_id).first()


def known_professionals(db: Session, patient: Patient) -> set[uuid.UUID]:
    return {
        staff_id
        for (staff_id,) in db.query(Appointment.staff_id)
        .filter(Appointment.patient_id == patient.id, Appointment.status.in_(PAST_RELATION))
        .distinct()
    }


def bookable_professionals(
    db: Session, *, clinic_id: uuid.UUID | str | None, appointment_type_id: uuid.UUID, patient: Patient | None
) -> list[tuple[Staff, str, bool]]:
    """Professionals with a schedule for this type, as (staff, name, known_to_patient).

    For a patient, professionals who do not accept new patients are left out unless the
    patient already had an appointment with them; known professionals come first.
    """
    rows = (
        db.query(Staff, User.full_name)
        .join(User, User.id == Staff.user_id)
        .join(ScheduleRule, ScheduleRule.staff_id == Staff.id)
        .join(ScheduleRuleType, ScheduleRuleType.rule_id == ScheduleRule.id)
        .filter(
            Staff.clinic_id == clinic_id,
            User.is_active.is_(True),
            ScheduleRuleType.appointment_type_id == appointment_type_id,
        )
        .distinct()
        .all()
    )
    known = known_professionals(db, patient) if patient is not None else set()
    result = [
        (staff, name, staff.id in known)
        for staff, name in rows
        if patient is None or staff.accepts_new_patients or staff.id in known
    ]
    return sorted(result, key=lambda row: (not row[2], row[1]))
