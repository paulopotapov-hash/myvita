"""Waiting list ("Fast Pass"): a patient with a booked appointment asks for an earlier slot
with the same professional or the same specialty.

When a slot is freed (a cancellation or a reschedule), every matching entry gets an offer
for it at the same time, valid for the clinic's `waitlist_offer_minutes`. Nothing is
assigned automatically: the first patient to accept gets the slot (the appointment
exclusion constraints decide a race) and their old appointment is cancelled in the same
transaction; the other offers for that slot close. There is no priority between patients
(no clinical criteria were defined): whoever accepts first.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.scheduling import _enum


class WaitlistScope(str, enum.Enum):
    PROFESSIONAL = "professional"  # the same professional
    SPECIALTY = "specialty"  # any eligible professional of the same specialty


class WaitlistStatus(str, enum.Enum):
    ACTIVE = "active"
    FULFILLED = "fulfilled"  # the patient accepted an offer
    LEFT = "left"  # the patient left the list
    CLOSED = "closed"  # the appointment was cancelled, moved, finished or has passed


class WaitlistOfferStatus(str, enum.Enum):
    OPEN = "open"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"
    CLOSED = "closed"  # taken by someone else, or the entry ended


class WaitlistEntry(Base):
    __tablename__ = "waitlist_entries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["patient_id", "clinic_id"], ["patients.id", "patients.clinic_id"], name="fk_waitlist_entries_patient_clinic", ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["appointment_id", "clinic_id"],
            ["appointments.id", "appointments.clinic_id"],
            name="fk_waitlist_entries_appointment_clinic",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["staff_id", "clinic_id"], ["staff.id", "staff.clinic_id"], name="fk_waitlist_entries_staff_clinic", ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["specialty_id", "clinic_id"],
            ["specialties.id", "specialties.clinic_id"],
            name="fk_waitlist_entries_specialty_clinic",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["appointment_type_id", "clinic_id"],
            ["appointment_types.id", "appointment_types.clinic_id"],
            name="fk_waitlist_entries_type_clinic",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "clinic_id", name="uq_waitlist_entries_id_clinic"),
        # One active entry per appointment (no duplicates, also under concurrent requests).
        Index("uq_waitlist_entries_active_appointment", "appointment_id", unique=True, postgresql_where=text("status = 'active'")),
        Index("ix_waitlist_entries_clinic_status", "clinic_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    appointment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    scope: Mapped[WaitlistScope] = mapped_column(_enum(WaitlistScope, "waitlist_scope"), nullable=False)
    # Copied from the appointment when joining: what an offered slot must match.
    staff_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    specialty_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    appointment_type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[WaitlistStatus] = mapped_column(
        _enum(WaitlistStatus, "waitlist_status"), nullable=False, default=WaitlistStatus.ACTIVE, server_default="active"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WaitlistOffer(Base):
    __tablename__ = "waitlist_offers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["entry_id", "clinic_id"], ["waitlist_entries.id", "waitlist_entries.clinic_id"], name="fk_waitlist_offers_entry_clinic", ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["staff_id", "clinic_id"], ["staff.id", "staff.clinic_id"], name="fk_waitlist_offers_staff_clinic", ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["new_appointment_id", "clinic_id"],
            ["appointments.id", "appointments.clinic_id"],
            name="fk_waitlist_offers_new_appointment_clinic",
            ondelete="RESTRICT",
        ),
        # The same slot is offered once per entry.
        UniqueConstraint("entry_id", "staff_id", "starts_at", name="uq_waitlist_offers_entry_slot"),
        CheckConstraint("ends_at > starts_at", name="ck_waitlist_offers_interval"),
        Index("ix_waitlist_offers_open_slot", "clinic_id", "staff_id", "starts_at", postgresql_where=text("status = 'open'")),
        Index("ix_waitlist_offers_open_expiry", "expires_at", postgresql_where=text("status = 'open'")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False)
    entry_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    staff_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[WaitlistOfferStatus] = mapped_column(
        _enum(WaitlistOfferStatus, "waitlist_offer_status"), nullable=False, default=WaitlistOfferStatus.OPEN, server_default="open"
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    new_appointment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
