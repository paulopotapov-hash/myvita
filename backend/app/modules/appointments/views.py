"""The patient's view of their appointments: display names only, never internal ids."""

import uuid

from sqlalchemy.orm import Session

from app.models import Appointment, AppointmentType, Clinic, Specialty, Staff, User
from app.modules.appointments.schemas import AppointmentPatientView

UNKNOWN_PROFESSIONAL = "Profissional de saúde"
DEFAULT_TYPE = "Consulta"


def patient_views(db: Session, appointments: list[Appointment]) -> list[AppointmentPatientView]:
    staff_ids = {appointment.staff_id for appointment in appointments}
    type_ids = {appointment.appointment_type_id for appointment in appointments if appointment.appointment_type_id}
    clinic_ids = {appointment.clinic_id for appointment in appointments}
    names: dict[uuid.UUID, str] = {}
    if staff_ids:
        names = {
            staff_id: name
            for staff_id, name in db.query(Staff.id, User.full_name).join(User, User.id == Staff.user_id).filter(Staff.id.in_(staff_ids))
        }
    types: dict[uuid.UUID, tuple[str, str | None]] = {}
    if type_ids:
        types = {
            type_id: (type_name, specialty_name)
            for type_id, type_name, specialty_name in db.query(AppointmentType.id, AppointmentType.name, Specialty.name)
            .join(Specialty, Specialty.id == AppointmentType.specialty_id)
            .filter(AppointmentType.id.in_(type_ids))
        }
    addresses: dict[uuid.UUID, str | None] = {}
    if clinic_ids:
        addresses = {clinic_id: address for clinic_id, address in db.query(Clinic.id, Clinic.address).filter(Clinic.id.in_(clinic_ids))}
    views = []
    for appointment in appointments:
        type_name, specialty = types.get(appointment.appointment_type_id, (DEFAULT_TYPE, None)) if appointment.appointment_type_id else (DEFAULT_TYPE, None)
        views.append(
            AppointmentPatientView(
                id=appointment.id,
                staff_name=names.get(appointment.staff_id, UNKNOWN_PROFESSIONAL),
                scheduled_at=appointment.scheduled_at,
                ends_at=appointment.ends_at,
                duration_minutes=appointment.duration_minutes,
                status=appointment.status,
                # A patient always reads the reason of their own appointment.
                reason=appointment.reason,
                appointment_type=type_name,
                specialty=specialty,
                location=addresses.get(appointment.clinic_id),
            )
        )
    return views
