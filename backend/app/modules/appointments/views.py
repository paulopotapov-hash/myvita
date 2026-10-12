"""The patient's view of their appointments: display names only, never internal ids."""

import uuid
from datetime import timedelta

from sqlalchemy.orm import Session

from app.models import (
    Appointment,
    AppointmentStatus,
    AppointmentType,
    BookingMode,
    Clinic,
    Specialty,
    Staff,
    User,
)
from app.models.scheduling import ClinicBookingSettings
from app.modules.appointments.schemas import AppointmentPatientView
from app.modules.scheduling import clock

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
    types: dict[uuid.UUID, tuple[str, str | None, BookingMode]] = {}
    if type_ids:
        types = {
            type_id: (type_name, specialty_name, mode)
            for type_id, type_name, specialty_name, mode in db.query(
                AppointmentType.id, AppointmentType.name, Specialty.name, AppointmentType.booking_mode
            )
            .join(Specialty, Specialty.id == AppointmentType.specialty_id)
            .filter(AppointmentType.id.in_(type_ids))
        }
    deadline_hours = {
        clinic_id: hours
        for clinic_id, hours in db.query(
            ClinicBookingSettings.clinic_id, ClinicBookingSettings.cancellation_deadline_hours
        ).filter(ClinicBookingSettings.clinic_id.in_(clinic_ids))
    }
    now = clock.now()
    addresses: dict[uuid.UUID, str | None] = {}
    if clinic_ids:
        addresses = {clinic_id: address for clinic_id, address in db.query(Clinic.id, Clinic.address).filter(Clinic.id.in_(clinic_ids))}
    views = []
    for appointment in appointments:
        type_name, specialty, mode = (
            types.get(appointment.appointment_type_id, (DEFAULT_TYPE, None, None))
            if appointment.appointment_type_id
            else (DEFAULT_TYPE, None, None)
        )
        hours = deadline_hours.get(appointment.clinic_id, ClinicBookingSettings.DEFAULT_CANCELLATION_DEADLINE_HOURS)
        active = appointment.status in (AppointmentStatus.SCHEDULED, AppointmentStatus.CONFIRMED)
        change_until = appointment.scheduled_at - timedelta(hours=hours) if active else None
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
                # The same rule the server applies (app/modules/scheduling/changes.py).
                can_change=change_until is not None and now < change_until,
                change_until=change_until,
                booking_mode=mode,
                patient_confirmed_at=appointment.patient_confirmed_at,
                can_confirm=active and appointment.patient_confirmed_at is None and now < appointment.scheduled_at,
            )
        )
    return views
