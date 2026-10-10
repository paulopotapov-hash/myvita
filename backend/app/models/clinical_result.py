import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
    inspect,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.database import Base


class ClinicalResultCategory(str, enum.Enum):
    LABORATORY = "laboratory"
    IMAGING = "imaging"
    PATHOLOGY = "pathology"
    OTHER = "other"


class ClinicalResultStatus(str, enum.Enum):
    """A result is prepared as a DRAFT (staff only) and RELEASED to the patient.

    Release is one-way: a released result is never edited or deleted. A
    correction is a new result that references the released one
    (`corrects_result_id`), so what the patient was shown is never overwritten.
    """

    DRAFT = "draft"
    RELEASED = "released"


class ClinicalResult(Base):
    """A clinical result (e.g. a laboratory value or an imaging conclusion).

    A result is not a document. It may *reference* an existing document of the
    same patient (for instance the laboratory's PDF report), which keeps its own
    storage, history and access rules.

    Immutability of released results is enforced in layers:
    - the services refuse it (409, audited as denied);
    - `_refuse_changes_to_released_results` below stops any ORM flush that
      would modify or delete a released row;
    - the database trigger `clinical_results_released_immutable` (migration
      8d9e0f1a2b3c) rejects every UPDATE or DELETE of a released row, including
      bulk/raw SQL by the application's runtime role;
    - the runtime role has no DELETE or TRUNCATE and may only UPDATE the columns
      a draft edit or a release writes (app/db_provisioning.py).
    Residual risk: the table owner (the migration role) or a superuser can
    disable or drop the trigger. This is not protection against a database
    administrator; that would need an external, append-only copy (a decision
    left for the security review).
    """

    __tablename__ = "clinical_results"
    __table_args__ = (
        # Target of the composite notification foreign key (same-clinic guarantee).
        UniqueConstraint("id", "clinic_id", name="uq_clinical_results_id_clinic"),
        # Target of the correction foreign key: a correction is for the same patient and clinic.
        UniqueConstraint("id", "patient_id", "clinic_id", name="uq_clinical_results_id_patient_clinic"),
        ForeignKeyConstraint(
            ["corrects_result_id", "patient_id", "clinic_id"],
            ["clinical_results.id", "clinical_results.patient_id", "clinical_results.clinic_id"],
            name="fk_clinical_results_corrects_same_patient",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patients.id", "patients.clinic_id"],
            name="fk_clinical_results_patient_clinic",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["author_staff_id", "clinic_id"],
            ["staff.id", "staff.clinic_id"],
            name="fk_clinical_results_author_clinic",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["released_by_staff_id", "clinic_id"],
            ["staff.id", "staff.clinic_id"],
            name="fk_clinical_results_releaser_clinic",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["document_id", "clinic_id"],
            ["documents.id", "documents.clinic_id"],
            name="fk_clinical_results_document_clinic",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(status = 'released' AND released_at IS NOT NULL AND released_by_staff_id IS NOT NULL) OR "
            "(status = 'draft' AND released_at IS NULL AND released_by_staff_id IS NULL)",
            name="ck_clinical_results_release_state",
        ),
        # A correction always says why; an original result never carries a reason.
        CheckConstraint(
            "(corrects_result_id IS NULL AND correction_reason IS NULL) OR "
            "(corrects_result_id IS NOT NULL AND correction_reason IS NOT NULL AND corrects_result_id <> id)",
            name="ck_clinical_results_correction",
        ),
        Index("ix_clinical_results_clinic_patient_date", "clinic_id", "patient_id", "result_date"),
        # Corrections form a chain: a result is corrected at most once (correct the latest version).
        Index(
            "uq_clinical_results_corrects_result_id",
            "corrects_result_id",
            unique=True,
            postgresql_where=text("corrects_result_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    author_staff_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    category: Mapped[ClinicalResultCategory] = mapped_column(
        Enum(
            ClinicalResultCategory,
            name="clinical_result_category",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    value: Mapped[str | None] = mapped_column(String(200), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reference_range: Mapped[str | None] = mapped_column(String(100), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_date: Mapped[date] = mapped_column(Date, nullable=False)
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[ClinicalResultStatus] = mapped_column(
        Enum(
            ClinicalResultStatus,
            name="clinical_result_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=ClinicalResultStatus.DRAFT,
    )
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_by_staff_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # Set on a correction: the released result it corrects, and the professional's reason.
    corrects_result_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    correction_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ReleasedResultImmutableError(RuntimeError):
    """Raised when code tries to modify or delete a released clinical result."""


@event.listens_for(Session, "before_flush")
def _refuse_changes_to_released_results(session: Session, _flush_context: object, _instances: object) -> None:
    """Last line of defence in the application: no code path may rewrite a released result.

    The draft -> released transition itself is allowed (the persisted status is
    still DRAFT); any later change, or a delete, of a row whose persisted status
    is RELEASED aborts the flush and therefore the transaction. The persisted
    status is read from the database, not from possibly expired ORM state.
    """
    deleted = {_identity(obj) for obj in session.deleted if isinstance(obj, ClinicalResult)}
    modified = {
        _identity(obj)
        for obj in session.dirty
        if isinstance(obj, ClinicalResult) and session.is_modified(obj)
    }
    ids = (deleted | modified) - {None}
    if not ids:
        return
    with session.no_autoflush:
        released = set(
            session.execute(
                select(ClinicalResult.id).where(
                    ClinicalResult.id.in_(ids), ClinicalResult.status == ClinicalResultStatus.RELEASED
                )
            ).scalars()
        )
    if deleted & released:
        raise ReleasedResultImmutableError("A released clinical result cannot be deleted.")
    if modified & released:
        raise ReleasedResultImmutableError("A released clinical result cannot be modified.")


def _identity(instance: ClinicalResult) -> uuid.UUID | None:
    """Primary key of a persistent row (None for a row not yet in the database)."""
    identity = inspect(instance).identity
    return identity[0] if identity is not None else None
