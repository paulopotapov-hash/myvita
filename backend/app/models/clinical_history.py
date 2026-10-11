"""Clinical history (commit 3): conditions, procedures, allergies, immunizations and notes.

One table for the five categories (decision D1), with a CHECK per category so a row
can only hold the fields its category uses. Medication stays in `medications`.

- Origin: a professional's entry is confirmed when created; a patient's declaration
  stays "Declarado pelo paciente" until a doctor or nurse confirms it.
- Partial dates (D5): each date is stored as the first day of its period together with
  its precision (year, month or day), so "2010" and "março 2010" stay what they are.
- Hidden from the patient (D4): a professional may hide one entry, with a reason;
  the patient never receives it while hidden.
- Soft delete: rows are never deleted (the runtime role has no DELETE privilege).
- Every change bumps `version` and writes an append-only revision in the same
  transaction; the audit log (separate transaction, D9) records who did what.
"""

import enum
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class HistoryCategory(str, enum.Enum):
    CONDITION = "condition"
    PROCEDURE = "procedure"
    ALLERGY = "allergy"
    IMMUNIZATION = "immunization"
    NOTE = "note"


class HistoryOrigin(str, enum.Enum):
    """Who created the entry. Shared with `medications`."""

    PROFESSIONAL = "professional"
    PATIENT_DECLARED = "patient_declared"


class ConditionStatus(str, enum.Enum):
    ACTIVE = "active"
    RESOLVED = "resolved"


class AllergySeverity(str, enum.Enum):
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"
    UNKNOWN = "unknown"


class DatePrecision(str, enum.Enum):
    YEAR = "year"
    MONTH = "month"
    DAY = "day"


class HistoryChangeKind(str, enum.Enum):
    CREATED = "created"
    UPDATED = "updated"
    CONFIRMED = "confirmed"
    HIDDEN = "hidden"
    SHOWN = "shown"
    DELETED = "deleted"


def _enum(enum_class: type[enum.Enum], name: str) -> Enum:
    return Enum(enum_class, name=name, values_callable=lambda e: [m.value for m in e])


HISTORY_ORIGIN_ENUM = _enum(HistoryOrigin, "history_origin")
DATE_PRECISION_ENUM = _enum(DatePrecision, "date_precision")

# Columns that only some categories use; a CHECK per category pins them.
_CATEGORY_COLUMNS = (
    "name",
    "condition_status",
    "onset_date",
    "resolved_date",
    "occurred_on",
    "location",
    "reaction",
    "severity",
    "note_text",
)
REQUIRED_FIELDS: dict[HistoryCategory, tuple[str, ...]] = {
    HistoryCategory.CONDITION: ("name", "condition_status"),
    HistoryCategory.PROCEDURE: ("name",),
    HistoryCategory.ALLERGY: ("name", "severity"),
    HistoryCategory.IMMUNIZATION: ("name",),
    HistoryCategory.NOTE: ("note_text",),
}
ALLOWED_FIELDS: dict[HistoryCategory, frozenset[str]] = {
    HistoryCategory.CONDITION: frozenset({"name", "condition_status", "onset_date", "resolved_date"}),
    HistoryCategory.PROCEDURE: frozenset({"name", "occurred_on", "location"}),
    HistoryCategory.ALLERGY: frozenset({"name", "reaction", "severity"}),
    HistoryCategory.IMMUNIZATION: frozenset({"name", "occurred_on"}),
    HistoryCategory.NOTE: frozenset({"note_text"}),
}


def _category_check(category: HistoryCategory) -> CheckConstraint:
    required = " AND ".join(f"{column} IS NOT NULL" for column in REQUIRED_FIELDS[category])
    unused = " AND ".join(
        f"{column} IS NULL" for column in _CATEGORY_COLUMNS if column not in ALLOWED_FIELDS[category]
    )
    return CheckConstraint(
        f"category <> '{category.value}' OR ({required} AND {unused})",
        name=f"ck_clinical_history_{category.value}_fields",
    )


def _precision_checks(column: str) -> list[CheckConstraint]:
    """A date always carries its precision, and is stored as the first day of its period."""
    precision = f"{column.removesuffix('_date').removesuffix('_on')}_precision"
    return [
        CheckConstraint(f"({column} IS NULL) = ({precision} IS NULL)", name=f"ck_clinical_history_{column}_precision"),
        CheckConstraint(
            f"{precision} IS DISTINCT FROM 'year' OR "
            f"(EXTRACT(MONTH FROM {column}) = 1 AND EXTRACT(DAY FROM {column}) = 1)",
            name=f"ck_clinical_history_{column}_year_start",
        ),
        CheckConstraint(
            f"{precision} IS DISTINCT FROM 'month' OR EXTRACT(DAY FROM {column}) = 1",
            name=f"ck_clinical_history_{column}_month_start",
        ),
    ]


class ClinicalHistoryEntry(Base):
    __tablename__ = "clinical_history_entries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patients.id", "patients.clinic_id"],
            name="fk_clinical_history_patient_clinic",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["confirmed_by_staff_id", "clinic_id"],
            ["staff.id", "staff.clinic_id"],
            name="fk_clinical_history_confirmed_staff_clinic",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["hidden_by_staff_id", "clinic_id"],
            ["staff.id", "staff.clinic_id"],
            name="fk_clinical_history_hidden_staff_clinic",
            ondelete="RESTRICT",
        ),
        # Target of the revisions' composite foreign key (same-clinic guarantee).
        UniqueConstraint("id", "clinic_id", name="uq_clinical_history_id_clinic"),
        Index(
            "ix_clinical_history_live_by_patient",
            "clinic_id",
            "patient_id",
            "category",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        *(_category_check(category) for category in HistoryCategory),
        CheckConstraint(
            "condition_status IS DISTINCT FROM 'active' OR resolved_date IS NULL",
            name="ck_clinical_history_active_not_resolved",
        ),
        CheckConstraint(
            "resolved_date IS NULL OR onset_date IS NULL OR resolved_date >= onset_date",
            name="ck_clinical_history_resolution_after_onset",
        ),
        *_precision_checks("onset_date"),
        *_precision_checks("resolved_date"),
        *_precision_checks("occurred_on"),
        # A professional's entry is confirmed when created; confirmation names who and when.
        CheckConstraint(
            "origin <> 'professional' OR confirmed_at IS NOT NULL", name="ck_clinical_history_professional_confirmed"
        ),
        CheckConstraint(
            "(confirmed_at IS NULL) = (confirmed_by_staff_id IS NULL)", name="ck_clinical_history_confirmation"
        ),
        CheckConstraint(
            "(hidden_at IS NULL) = (hidden_by_staff_id IS NULL) AND (hidden_at IS NULL) = (hidden_reason IS NULL)",
            name="ck_clinical_history_hidden",
        ),
        CheckConstraint(
            "(deleted_at IS NULL) = (deleted_by_user_id IS NULL) AND (deleted_at IS NOT NULL OR deletion_reason IS NULL)",
            name="ck_clinical_history_deleted",
        ),
        CheckConstraint("version >= 1", name="ck_clinical_history_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    category: Mapped[HistoryCategory] = mapped_column(_enum(HistoryCategory, "history_category"), nullable=False)

    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    condition_status: Mapped[ConditionStatus | None] = mapped_column(
        _enum(ConditionStatus, "condition_status"), nullable=True
    )
    onset_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    onset_precision: Mapped[DatePrecision | None] = mapped_column(DATE_PRECISION_ENUM, nullable=True)
    resolved_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    resolved_precision: Mapped[DatePrecision | None] = mapped_column(DATE_PRECISION_ENUM, nullable=True)
    occurred_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    occurred_precision: Mapped[DatePrecision | None] = mapped_column(DATE_PRECISION_ENUM, nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reaction: Mapped[str | None] = mapped_column(String(500), nullable=True)
    severity: Mapped[AllergySeverity | None] = mapped_column(_enum(AllergySeverity, "allergy_severity"), nullable=True)
    note_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    origin: Mapped[HistoryOrigin] = mapped_column(HISTORY_ORIGIN_ENUM, nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    confirmed_by_staff_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hidden_by_staff_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hidden_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    deletion_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class ClinicalHistoryRevision(Base):
    """Append-only snapshot of an entry at each version (the runtime role may only insert)."""

    __tablename__ = "clinical_history_revisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["entry_id", "clinic_id"],
            ["clinical_history_entries.id", "clinical_history_entries.clinic_id"],
            name="fk_clinical_history_revisions_entry_clinic",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("entry_id", "version", name="uq_clinical_history_revisions_entry_version"),
        CheckConstraint("version >= 1", name="ck_clinical_history_revisions_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False
    )
    entry_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    change_kind: Mapped[HistoryChangeKind] = mapped_column(
        _enum(HistoryChangeKind, "history_change_kind"), nullable=False
    )
    changed_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    change_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
