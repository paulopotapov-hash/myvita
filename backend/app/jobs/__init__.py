"""Background jobs (`python -m app.jobs`, see __main__.py): scheduling (step 7), and the
retry of patient-photo file deletions that failed."""

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import Appointment, AppointmentStatus, WaitlistEntry, WaitlistStatus
from app.modules.patient_photos.service import retry_file_deletions
from app.modules.scheduling import clock, reminders, waitlist

logger = logging.getLogger("myvita.jobs")
# One runner at a time across processes and containers (session-level advisory lock).
LOCK_KEY = "myvita:scheduling-jobs"


@dataclass(frozen=True)
class TickResult:
    ran: bool
    reminders: int = 0
    expired_offers: int = 0
    closed_entries: int = 0
    deleted_files: int = 0


def close_past_entries(db: Session, now: datetime) -> int:
    """Waiting-list entries whose appointment has started or is no longer active close,
    with their open offers."""
    appointment_ids = [
        appointment_id
        for (appointment_id,) in db.query(WaitlistEntry.appointment_id)
        .join(Appointment, Appointment.id == WaitlistEntry.appointment_id)
        .filter(
            WaitlistEntry.status == WaitlistStatus.ACTIVE,
            (Appointment.scheduled_at <= now) | Appointment.status.not_in((AppointmentStatus.SCHEDULED, AppointmentStatus.CONFIRMED)),
        )
    ]
    for appointment_id in appointment_ids:
        waitlist.close_for_appointment(db, appointment_id)
    db.commit()
    return len(appointment_ids)


def run_once(db: Session) -> TickResult:
    """One pass of every job, if no other runner holds the lock. Logs counts only.

    The lock lives on its own connection: the session returns its connection to the pool
    at every commit, and a session-level advisory lock belongs to one connection."""
    with db.get_bind().engine.connect() as lock:
        acquired = lock.execute(text("SELECT pg_try_advisory_lock(hashtextextended(:key, 0))"), {"key": LOCK_KEY}).scalar_one()
        lock.commit()
        if not acquired:
            return TickResult(ran=False)
        try:
            now = clock.now()
            result = TickResult(
                ran=True,
                reminders=reminders.send_due_reminders(db, now),
                expired_offers=waitlist.expire_offers(db),
                closed_entries=close_past_entries(db, now),
                deleted_files=retry_file_deletions(db),
            )
            logger.info(
                "scheduling_jobs reminders=%d expired_offers=%d closed_entries=%d deleted_files=%d",
                result.reminders,
                result.expired_offers,
                result.closed_entries,
                result.deleted_files,
            )
            return result
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(hashtextextended(:key, 0))"), {"key": LOCK_KEY})
            lock.commit()
