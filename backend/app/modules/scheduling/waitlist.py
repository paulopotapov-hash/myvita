"""The waiting list ("Fast Pass"): see app/models/waitlist.py for the rules.

- Joining: the patient's own active appointment of a direct type, before the clinic's
  deadline; the same professional or the same specialty; one active entry per
  appointment (partial unique index, so also under concurrent requests).
- Offers are created in the transaction that frees a slot (`offer_freed_slot`, called by
  every cancellation path): each active entry whose appointment is later than the freed
  slot, that the slot fits (the professional offers that type then, and is eligible for
  the patient) and whose patient is free then, gets an offer valid for the clinic's
  `waitlist_offer_minutes` (never past the slot itself), and an in-app notification.
- Accepting books the slot and cancels the old appointment in one transaction under the
  clinic lock (shared with rescheduling); the exclusion constraints make sure only the
  first acceptance wins. The other offers for that slot close.
- An entry closes when its appointment stops being active (cancelled, moved, finished).
  Expired offers are closed by the background job; until then they count as expired.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Appointment,
    AppointmentStatus,
    AppointmentType,
    BookingMode,
    BookingSource,
    Patient,
    Staff,
    User,
    WaitlistEntry,
    WaitlistOffer,
    WaitlistOfferStatus,
    WaitlistScope,
    WaitlistStatus,
)
from app.modules.notifications.events import NotificationEvent, notify
from app.modules.scheduling import clock, service
from app.modules.scheduling.availability import Slot, patient_busy_intervals, slot_is_free
from app.modules.scheduling.booking import AutoAssignment, booking_guard
from app.modules.scheduling.eligibility import bookable_professionals

ACTIVE = (AppointmentStatus.SCHEDULED, AppointmentStatus.CONFIRMED)
ALREADY_LISTED = "Já estás na lista de espera para esta consulta."
DIRECT_ONLY = "A lista de espera é para consultas de marcação direta."
OFFER_GONE = "Esta vaga já não está disponível."
_NOT_FOUND = "Não encontrado."


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)


def _patient(db: Session, user: User) -> Patient:
    patient = db.query(Patient).filter(Patient.user_id == user.id, Patient.clinic_id == user.clinic_id).first()
    if patient is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Só pacientes usam a lista de espera.")
    return patient


def join(db: Session, user: User, appointment_id: uuid.UUID, scope: WaitlistScope) -> WaitlistEntry:
    from app.modules.scheduling.changes import own_appointment, require_changeable

    patient = _patient(db, user)
    appointment = own_appointment(db, patient, appointment_id)
    require_changeable(db, appointment)
    appointment_type = db.get(AppointmentType, appointment.appointment_type_id) if appointment.appointment_type_id else None
    if appointment_type is None or appointment_type.booking_mode != BookingMode.DIRECT:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=DIRECT_ONLY)
    entry = WaitlistEntry(
        clinic_id=patient.clinic_id,
        patient_id=patient.id,
        appointment_id=appointment.id,
        scope=scope,
        staff_id=appointment.staff_id,
        specialty_id=appointment_type.specialty_id,
        appointment_type_id=appointment_type.id,
    )
    db.add(entry)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=ALREADY_LISTED) from exc
    db.refresh(entry)
    return entry


def _close_offers(db: Session, entry_ids: list[uuid.UUID], at: datetime) -> None:
    if not entry_ids:
        return
    db.query(WaitlistOffer).filter(
        WaitlistOffer.entry_id.in_(entry_ids), WaitlistOffer.status == WaitlistOfferStatus.OPEN
    ).update({WaitlistOffer.status: WaitlistOfferStatus.CLOSED, WaitlistOffer.decided_at: at}, synchronize_session="fetch")


def leave(db: Session, user: User, entry_id: uuid.UUID) -> WaitlistEntry:
    patient = _patient(db, user)
    entry = (
        db.query(WaitlistEntry)
        .filter(WaitlistEntry.id == entry_id, WaitlistEntry.patient_id == patient.id, WaitlistEntry.clinic_id == patient.clinic_id)
        .with_for_update()
        .first()
    )
    if entry is None:
        raise _not_found()
    if entry.status != WaitlistStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Já não estás na lista de espera.")
    at = clock.now()
    entry.status, entry.ended_at = WaitlistStatus.LEFT, at
    _close_offers(db, [entry.id], at)
    db.commit()
    db.refresh(entry)
    return entry


def close_for_appointment(db: Session, appointment_id: uuid.UUID) -> None:
    """The appointment is no longer active: its entry (if any) ends, with its open offers."""
    at = clock.now()
    entries = (
        db.query(WaitlistEntry)
        .filter(WaitlistEntry.appointment_id == appointment_id, WaitlistEntry.status == WaitlistStatus.ACTIVE)
        .all()
    )
    for entry in entries:
        entry.status, entry.ended_at = WaitlistStatus.CLOSED, at
    _close_offers(db, [entry.id for entry in entries], at)


@dataclass(frozen=True)
class FreedSlot:
    """Where an appointment was before it was cancelled or moved."""

    clinic_id: uuid.UUID
    patient_id: uuid.UUID
    staff_id: uuid.UUID
    scheduled_at: datetime


def offer_freed_slot(db: Session, freed: Appointment | FreedSlot) -> list[WaitlistOffer]:
    """Offer the slot just released (the change is already flushed) to matching entries."""
    at = clock.now()
    if freed.scheduled_at <= at:
        return []
    freed_staff = db.get(Staff, freed.staff_id)
    if freed_staff is None:
        return []
    entries = (
        db.query(WaitlistEntry, Appointment, Patient)
        .join(Appointment, Appointment.id == WaitlistEntry.appointment_id)
        .join(Patient, Patient.id == WaitlistEntry.patient_id)
        .filter(
            WaitlistEntry.clinic_id == freed.clinic_id,
            WaitlistEntry.status == WaitlistStatus.ACTIVE,
            WaitlistEntry.patient_id != freed.patient_id,
            Appointment.status.in_(ACTIVE),
            Appointment.scheduled_at > freed.scheduled_at,
            (WaitlistEntry.staff_id == freed_staff.id)
            | ((WaitlistEntry.scope == WaitlistScope.SPECIALTY) & (WaitlistEntry.specialty_id == freed_staff.specialty_id)),
        )
        .order_by(WaitlistEntry.created_at)
        .all()
    )
    if not entries:
        return []
    minutes = service.get_settings(db, freed.clinic_id).waitlist_offer_minutes
    offers: list[WaitlistOffer] = []
    for entry, current, patient in entries:
        if entry.scope == WaitlistScope.PROFESSIONAL and entry.staff_id != freed_staff.id:
            continue
        appointment_type = db.get(AppointmentType, entry.appointment_type_id)
        if appointment_type is None or not appointment_type.active:
            continue
        eligible = {staff.id for staff, _name, _known in bookable_professionals(
            db, clinic_id=freed.clinic_id, appointment_type_id=appointment_type.id, patient=patient
        )}
        if freed_staff.id not in eligible:
            continue
        if not slot_is_free(
            db, clinic_id=freed.clinic_id, appointment_type=appointment_type, staff_id=freed_staff.id, starts_at=freed.scheduled_at, now=at
        ):
            continue
        ends_at = freed.scheduled_at + timedelta(minutes=appointment_type.duration_minutes)
        busy = patient_busy_intervals(
            db, patient.id, [Slot(starts_at=freed.scheduled_at, ends_at=ends_at, staff_id=freed_staff.id)], ignore_appointment_id=current.id
        )
        if busy:
            continue
        exists = (
            db.query(WaitlistOffer.id)
            .filter(WaitlistOffer.entry_id == entry.id, WaitlistOffer.staff_id == freed_staff.id, WaitlistOffer.starts_at == freed.scheduled_at)
            .first()
        )
        if exists is not None:
            continue
        offer = WaitlistOffer(
            clinic_id=freed.clinic_id,
            entry_id=entry.id,
            staff_id=freed_staff.id,
            starts_at=freed.scheduled_at,
            ends_at=ends_at,
            expires_at=min(at + timedelta(minutes=minutes), freed.scheduled_at),
        )
        db.add(offer)
        db.flush()
        notify(
            db,
            NotificationEvent.WAITLIST_OFFER,
            clinic_id=freed.clinic_id,
            recipient_user_id=patient.user_id,
            dedupe_key=str(offer.id),
        )
        offers.append(offer)
    return offers


def _own_offer(db: Session, patient: Patient, offer_id: uuid.UUID) -> tuple[WaitlistOffer, WaitlistEntry]:
    row = (
        db.query(WaitlistOffer, WaitlistEntry)
        .join(WaitlistEntry, WaitlistEntry.id == WaitlistOffer.entry_id)
        .filter(WaitlistOffer.id == offer_id, WaitlistEntry.patient_id == patient.id, WaitlistEntry.clinic_id == patient.clinic_id)
        .with_for_update(of=WaitlistOffer)
        .first()
    )
    if row is None:
        raise _not_found()
    return row[0], row[1]


def accept_offer(
    db: Session, user: User, offer_id: uuid.UUID
) -> tuple[Appointment, Appointment, AutoAssignment | None, AutoAssignment | None]:
    """Returns (new appointment, old appointment, care link created, care link ended)."""
    patient = _patient(db, user)
    try:
        return _accept(db, user, patient, offer_id)
    except HTTPException:
        db.rollback()  # the old appointment and the offer stay as they were
        raise


def _accept(
    db: Session, user: User, patient: Patient, offer_id: uuid.UUID
) -> tuple[Appointment, Appointment, AutoAssignment | None, AutoAssignment | None]:
    from app.modules.appointments.service import lock_clinic_schedule
    from app.modules.scheduling.changes import book_replacement

    with booking_guard(db, patient_facing=True):
        lock_clinic_schedule(db, patient.clinic_id)
        offer, entry = _own_offer(db, patient, offer_id)
        at = clock.now()
        if offer.status != WaitlistOfferStatus.OPEN or offer.expires_at <= at or entry.status != WaitlistStatus.ACTIVE:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=OFFER_GONE)
        old = db.get(Appointment, entry.appointment_id)
        appointment_type = db.get(AppointmentType, entry.appointment_type_id)
        if old is None or old.status not in ACTIVE or appointment_type is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=OFFER_GONE)
        new, created, ended = book_replacement(
            db,
            user=user,
            patient=patient,
            old=old,
            appointment_type=appointment_type,
            candidates=[offer.staff_id],
            starts_at=offer.starts_at,
            booked_via=BookingSource.WAITLIST,
            at=at,
        )
        # Freeing the old appointment closed this entry and its offers: record the outcome.
        offer.status, offer.decided_at, offer.new_appointment_id = WaitlistOfferStatus.ACCEPTED, at, new.id
        entry.status, entry.ended_at = WaitlistStatus.FULFILLED, at
        db.query(WaitlistOffer).filter(
            WaitlistOffer.clinic_id == patient.clinic_id,
            WaitlistOffer.staff_id == offer.staff_id,
            WaitlistOffer.status == WaitlistOfferStatus.OPEN,
            WaitlistOffer.starts_at < new.ends_at,
            WaitlistOffer.ends_at > new.scheduled_at,
        ).update({WaitlistOffer.status: WaitlistOfferStatus.CLOSED, WaitlistOffer.decided_at: at}, synchronize_session="fetch")
        db.commit()
    db.refresh(new)
    db.refresh(old)
    return new, old, created, ended


def decline_offer(db: Session, user: User, offer_id: uuid.UUID) -> WaitlistOffer:
    patient = _patient(db, user)
    offer, _entry = _own_offer(db, patient, offer_id)
    if offer.status != WaitlistOfferStatus.OPEN:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=OFFER_GONE)
    offer.status, offer.decided_at = WaitlistOfferStatus.DECLINED, clock.now()
    db.commit()
    db.refresh(offer)
    return offer


def expire_offers(db: Session) -> int:
    """Close offers past their expiry (background job). Returns how many."""
    at = clock.now()
    count = (
        db.query(WaitlistOffer)
        .filter(WaitlistOffer.status == WaitlistOfferStatus.OPEN, WaitlistOffer.expires_at <= at)
        .update({WaitlistOffer.status: WaitlistOfferStatus.EXPIRED, WaitlistOffer.decided_at: at}, synchronize_session=False)
    )
    db.commit()
    return count


def list_for_patient(db: Session, user: User) -> list[tuple[WaitlistEntry, list[tuple[WaitlistOffer, str]]]]:
    """The patient's active entries, each with its open, unexpired offers (and professional names)."""
    patient = _patient(db, user)
    at = clock.now()
    entries = (
        db.query(WaitlistEntry)
        .filter(WaitlistEntry.patient_id == patient.id, WaitlistEntry.status == WaitlistStatus.ACTIVE)
        .order_by(WaitlistEntry.created_at)
        .all()
    )
    result = []
    for entry in entries:
        offers = (
            db.query(WaitlistOffer, User.full_name)
            .join(Staff, Staff.id == WaitlistOffer.staff_id)
            .join(User, User.id == Staff.user_id)
            .filter(WaitlistOffer.entry_id == entry.id, WaitlistOffer.status == WaitlistOfferStatus.OPEN, WaitlistOffer.expires_at > at)
            .order_by(WaitlistOffer.starts_at)
            .all()
        )
        result.append((entry, [(offer, name) for offer, name in offers]))
    return result
