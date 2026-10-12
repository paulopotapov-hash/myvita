"""Appointment reminders (step 7), sent by the background job (python -m app.jobs).

Each active appointment gets ONE in-app reminder once it is within the clinic's
`reminder_hours_before` of its start: a notification linked to the appointment, where the
patient confirms they will come or (before the deadline) cancels. The delivery row and
the notification are written in one transaction, and the unique (appointment, channel)
row makes the job idempotent: running it twice, or in two processes, sends one reminder.

Email and SMS are prepared but not active (app/models/reminder.py): `ACTIVE_CHANNELS`
holds only the in-app channel, and nothing else is attempted or recorded.
"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import (
    Appointment,
    AppointmentStatus,
    ClinicBookingSettings,
    Patient,
    ReminderChannel,
    ReminderDelivery,
    ReminderStatus,
)
from app.modules.notifications.events import NotificationEvent, NotificationTarget, TargetType, notify

ACTIVE_CHANNELS = (ReminderChannel.IN_APP,)
ACTIVE = (AppointmentStatus.SCHEDULED, AppointmentStatus.CONFIRMED)
BATCH = 200


def due_appointments(db: Session, now: datetime) -> list[Appointment]:
    """Active appointments within their clinic's reminder window, without an in-app reminder."""
    hours = func.coalesce(ClinicBookingSettings.reminder_hours_before, ClinicBookingSettings.DEFAULT_REMINDER_HOURS_BEFORE)
    already = select(ReminderDelivery.appointment_id).where(ReminderDelivery.channel == ReminderChannel.IN_APP)
    return (
        db.query(Appointment)
        .outerjoin(ClinicBookingSettings, ClinicBookingSettings.clinic_id == Appointment.clinic_id)
        .filter(
            Appointment.status.in_(ACTIVE),
            Appointment.scheduled_at > now,
            Appointment.scheduled_at <= now + func.make_interval(0, 0, 0, 0, hours),
            Appointment.id.not_in(already),
        )
        .order_by(Appointment.scheduled_at)
        .limit(BATCH)
        .all()
    )


def send_due_reminders(db: Session, now: datetime) -> int:
    """Send the reminders that are due; returns how many went out."""
    sent = 0
    for appointment in due_appointments(db, now):
        inserted = db.execute(
            insert(ReminderDelivery)
            .values(
                clinic_id=appointment.clinic_id,
                appointment_id=appointment.id,
                channel=ReminderChannel.IN_APP,
                status=ReminderStatus.SENT,
            )
            .on_conflict_do_nothing(constraint="uq_reminder_deliveries_appointment_channel")
            .returning(ReminderDelivery.id)
        ).scalar_one_or_none()
        if inserted is None:
            continue  # another run sent it
        patient = db.get(Patient, appointment.patient_id)
        if patient is not None:
            notify(
                db,
                NotificationEvent.APPOINTMENT_REMINDER,
                clinic_id=appointment.clinic_id,
                recipient_user_id=patient.user_id,
                target=NotificationTarget(TargetType.APPOINTMENT, appointment.id),
                dedupe_key=str(appointment.id),
            )
        db.commit()
        sent += 1
    return sent
