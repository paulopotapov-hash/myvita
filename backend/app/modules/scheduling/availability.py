"""Free slots: weekly schedules minus absences minus active appointments.

Schedules are wall-clock hours in Europe/Lisbon; each candidate slot is built in local
time and converted to UTC, so the 09:00 block stays at 09:00 local across daylight-saving
changes. A slot is the appointment type's duration, back to back inside each block.

This is a read model only: booking re-checks everything under a lock and the database
exclusion constraints decide (a slot shown here may be taken a second later).
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models import (
    CLINIC_TIME_ZONE,
    Appointment,
    AppointmentStatus,
    AppointmentType,
    ScheduleAbsence,
    ScheduleRule,
    ScheduleRuleType,
)

TZ = ZoneInfo(CLINIC_TIME_ZONE)
MAX_RANGE_DAYS = 31
ACTIVE = (AppointmentStatus.SCHEDULED, AppointmentStatus.CONFIRMED)


@dataclass(frozen=True)
class Slot:
    starts_at: datetime
    ends_at: datetime
    staff_id: uuid.UUID


def local_day_bounds(day_from: date, day_to: date) -> tuple[datetime, datetime]:
    """[day_from 00:00, day_to + 1 00:00) in Lisbon, as UTC instants."""
    start = datetime.combine(day_from, time.min, tzinfo=TZ).astimezone(UTC)
    end = datetime.combine(day_to + timedelta(days=1), time.min, tzinfo=TZ).astimezone(UTC)
    return start, end


def _local(day: date, at: time) -> datetime:
    return datetime.combine(day, at, tzinfo=TZ).astimezone(UTC)


def _busy(intervals: list[tuple[datetime, datetime]], start: datetime, end: datetime) -> bool:
    return any(busy_start < end and busy_end > start for busy_start, busy_end in intervals)


def free_slots(
    db: Session,
    *,
    clinic_id: uuid.UUID,
    appointment_type: AppointmentType,
    staff_ids: list[uuid.UUID],
    day_from: date,
    day_to: date,
    now: datetime | None = None,
    ignore_appointment_id: uuid.UUID | None = None,
) -> list[Slot]:
    """`ignore_appointment_id`: the appointment being rescheduled, whose time is offered again."""
    if not staff_ids or day_to < day_from:
        return []
    now = now or datetime.now(UTC)
    range_start, range_end = local_day_bounds(day_from, day_to)
    duration = timedelta(minutes=appointment_type.duration_minutes)

    rules = (
        db.query(ScheduleRule)
        .join(ScheduleRuleType, ScheduleRuleType.rule_id == ScheduleRule.id)
        .filter(
            ScheduleRule.clinic_id == clinic_id,
            ScheduleRule.staff_id.in_(staff_ids),
            ScheduleRuleType.appointment_type_id == appointment_type.id,
        )
        .all()
    )
    busy: dict[uuid.UUID, list[tuple[datetime, datetime]]] = defaultdict(list)
    for absence in db.query(ScheduleAbsence).filter(
        ScheduleAbsence.clinic_id == clinic_id,
        ScheduleAbsence.staff_id.in_(staff_ids),
        ScheduleAbsence.starts_at < range_end,
        ScheduleAbsence.ends_at > range_start,
    ):
        busy[absence.staff_id].append((absence.starts_at, absence.ends_at))
    appointments = db.query(Appointment).filter(
        Appointment.clinic_id == clinic_id,
        Appointment.staff_id.in_(staff_ids),
        Appointment.status.in_(ACTIVE),
        Appointment.scheduled_at < range_end,
        Appointment.ends_at > range_start,
    )
    if ignore_appointment_id is not None:
        appointments = appointments.filter(Appointment.id != ignore_appointment_id)
    for appointment in appointments:
        busy[appointment.staff_id].append((appointment.scheduled_at, appointment.ends_at))

    slots: list[Slot] = []
    day = day_from
    while day <= day_to:
        for rule in rules:
            if rule.weekday != day.weekday():
                continue
            if (rule.valid_from and day < rule.valid_from) or (rule.valid_until and day > rule.valid_until):
                continue
            start, block_end = _local(day, rule.start_time), _local(day, rule.end_time)
            while start + duration <= block_end:
                end = start + duration
                if start > now and not _busy(busy[rule.staff_id], start, end):
                    slots.append(Slot(starts_at=start, ends_at=end, staff_id=rule.staff_id))
                start = end
        day += timedelta(days=1)
    # Overlapping blocks of the same professional never yield the same slot twice.
    unique = {(slot.staff_id, slot.starts_at): slot for slot in slots}
    return sorted(unique.values(), key=lambda slot: (slot.starts_at, str(slot.staff_id)))


def patient_busy_intervals(
    db: Session, patient_id: uuid.UUID, slots: list[Slot], ignore_appointment_id: uuid.UUID | None = None
) -> list[tuple[datetime, datetime]]:
    """The patient's active appointments within the span of `slots`."""
    if not slots:
        return []
    start = min(slot.starts_at for slot in slots)
    end = max(slot.ends_at for slot in slots)
    query = db.query(Appointment.scheduled_at, Appointment.ends_at).filter(
        Appointment.patient_id == patient_id,
        Appointment.status.in_(ACTIVE),
        Appointment.scheduled_at < end,
        Appointment.ends_at > start,
    )
    if ignore_appointment_id is not None:
        query = query.filter(Appointment.id != ignore_appointment_id)
    return [(scheduled_at, ends_at) for scheduled_at, ends_at in query]


def slot_is_free(
    db: Session,
    *,
    clinic_id: uuid.UUID,
    appointment_type: AppointmentType,
    staff_id: uuid.UUID,
    starts_at: datetime,
    now: datetime | None = None,
) -> bool:
    """Whether `starts_at` is one of the professional's offered slots for this type right now."""
    local_day = starts_at.astimezone(TZ).date()
    return any(
        slot.starts_at == starts_at
        for slot in free_slots(
            db,
            clinic_id=clinic_id,
            appointment_type=appointment_type,
            staff_ids=[staff_id],
            day_from=local_day,
            day_to=local_day,
            now=now,
        )
    )
