"""Clinical history entries: who may do what, validation per category, revisions.

Permissions (central policy, app/core/clinical_access.py):
- doctors and nurses with an active care assignment: create (confirmed at once),
  edit, confirm, hide from the patient with a reason (D4), show again, delete
  with a reason, read the revisions;
- the patient: read their own entries that are not hidden, declare new ones,
  and edit or delete their own declarations until a professional confirms them (D3);
- everyone else: nothing (403), and other clinics' patients do not exist (404).

Every change locks the row, checks `expected_version`, bumps the version and
writes an append-only revision in the same transaction.
"""

import uuid
from collections.abc import Iterable
from datetime import UTC, date, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, nulls_last
from sqlalchemy.orm import Session

from app.core.clinical_access import ClinicalAction, clinical_access, clinical_staff
from app.core.partial_dates import PartialDateError, format_partial_date, parse_partial_date
from app.models import (
    ClinicalHistoryEntry,
    ClinicalHistoryRevision,
    ConditionStatus,
    HistoryCategory,
    HistoryChangeKind,
    HistoryOrigin,
    Staff,
    User,
    UserRole,
)
from app.models.clinical_history import ALLOWED_FIELDS, REQUIRED_FIELDS
from app.modules.clinical_history.schemas import (
    ClinicalHistoryCreateRequest,
    ClinicalHistoryUpdateRequest,
    DeleteRequest,
    HideRequest,
    VersionedRequest,
)

NOT_FOUND = "Entrada do histórico não encontrada."
PATIENT_LOCKED = "Só podes alterar as tuas declarações ainda não confirmadas por um profissional."
STALE = "A entrada foi alterada entretanto. Atualiza a página e tenta de novo."

# API field -> (date column, precision column).
DATE_FIELDS = {
    "onset": ("onset_date", "onset_precision"),
    "resolved": ("resolved_date", "resolved_precision"),
    "occurred": ("occurred_on", "occurred_precision"),
}
CONTENT_FIELDS = ("name", "condition_status", "onset", "resolved", "occurred", "location", "reaction", "severity", "note_text")
_DB_NAME = {"onset": "onset_date", "resolved": "resolved_date", "occurred": "occurred_on"}


def _field_errors(errors: dict[str, str]) -> HTTPException:
    detail = [{"type": "value_error", "loc": ["body", field], "msg": message} for field, message in errors.items()]
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


def _validated_columns(category: HistoryCategory, values: dict[str, Any]) -> dict[str, Any]:
    """API values (after merging) -> column values, or 422 naming each wrong field."""
    errors: dict[str, str] = {}
    values = {key: (None if isinstance(value, str) and not value.strip() else value) for key, value in values.items()}
    allowed = ALLOWED_FIELDS[category]
    for field in CONTENT_FIELDS:
        if values.get(field) is not None and _DB_NAME.get(field, field) not in allowed:
            errors[field] = "Este campo não se aplica a esta categoria."
    for field in REQUIRED_FIELDS[category]:
        if values.get(field) is None:
            errors[field] = "Campo obrigatório."

    columns: dict[str, Any] = {field: values.get(field) for field in CONTENT_FIELDS if field not in DATE_FIELDS}
    starts: dict[str, date] = {}
    for field, (date_column, precision_column) in DATE_FIELDS.items():
        columns[date_column] = columns[precision_column] = None
        raw = values.get(field)
        if raw is None or field in errors:
            continue
        try:
            parsed, precision = parse_partial_date(raw)
        except PartialDateError as exc:
            errors[field] = str(exc)
            continue
        columns[date_column], columns[precision_column] = parsed, precision
        starts[field] = parsed

    if category == HistoryCategory.CONDITION:
        if values.get("condition_status") == ConditionStatus.ACTIVE and values.get("resolved") is not None:
            errors.setdefault("resolved", "Só uma doença resolvida tem data de resolução.")
        if "onset" in starts and "resolved" in starts and starts["resolved"] < starts["onset"]:
            errors.setdefault("resolved", "A resolução não pode ser anterior ao início.")
    if errors:
        raise _field_errors(errors)
    return columns


def _api_values(entry: ClinicalHistoryEntry) -> dict[str, Any]:
    values: dict[str, Any] = {
        field: getattr(entry, field) for field in CONTENT_FIELDS if field not in DATE_FIELDS
    }
    for field, (date_column, precision_column) in DATE_FIELDS.items():
        values[field] = format_partial_date(getattr(entry, date_column), getattr(entry, precision_column))
    return values


def snapshot(entry: ClinicalHistoryEntry) -> dict[str, Any]:
    """Revision content: what the entry said and its state at this version (JSON-safe)."""

    def plain(value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        return getattr(value, "value", value)

    state = {
        "category": entry.category,
        "origin": entry.origin,
        "confirmed_at": entry.confirmed_at,
        "hidden_at": entry.hidden_at,
        "hidden_reason": entry.hidden_reason,
        "deleted_at": entry.deleted_at,
    }
    return {key: plain(value) for key, value in {**_api_values(entry), **state}.items()}


def _revise(db: Session, entry: ClinicalHistoryEntry, user: User, kind: HistoryChangeKind, reason: str | None = None) -> None:
    db.flush()
    db.add(
        ClinicalHistoryRevision(
            clinic_id=entry.clinic_id,
            entry_id=entry.id,
            version=entry.version,
            change_kind=kind,
            changed_by_user_id=user.id,
            change_reason=reason,
            snapshot=snapshot(entry),
        )
    )


def _now() -> datetime:
    return datetime.now(UTC)


def is_own_open_declaration(entry: ClinicalHistoryEntry, user: User) -> bool:
    return (
        user.role == UserRole.PATIENT
        and entry.origin == HistoryOrigin.PATIENT_DECLARED
        and entry.created_by_user_id == user.id
        and entry.confirmed_at is None
    )


# --- reading ----------------------------------------------------------------------------------


def list_entries(
    db: Session, patient_id: uuid.UUID, user: User, category: HistoryCategory | None = None
) -> list[ClinicalHistoryEntry]:
    patient = clinical_access(db, patient_id, user, ClinicalAction.VIEW_CLINICAL_HISTORY)
    query = db.query(ClinicalHistoryEntry).filter(
        ClinicalHistoryEntry.clinic_id == patient.clinic_id,
        ClinicalHistoryEntry.patient_id == patient.id,
        ClinicalHistoryEntry.deleted_at.is_(None),
    )
    if user.role == UserRole.PATIENT:
        query = query.filter(ClinicalHistoryEntry.hidden_at.is_(None))
    if category is not None:
        query = query.filter(ClinicalHistoryEntry.category == category)
    most_recent = func.coalesce(
        ClinicalHistoryEntry.occurred_on, ClinicalHistoryEntry.onset_date, func.date(ClinicalHistoryEntry.created_at)
    )
    return query.order_by(
        ClinicalHistoryEntry.category, nulls_last(most_recent.desc()), ClinicalHistoryEntry.created_at.desc()
    ).all()


def _load(db: Session, entry_id: uuid.UUID, user: User, *, lock: bool = False) -> ClinicalHistoryEntry:
    query = db.query(ClinicalHistoryEntry).filter(
        ClinicalHistoryEntry.id == entry_id,
        ClinicalHistoryEntry.clinic_id == user.clinic_id,
        ClinicalHistoryEntry.deleted_at.is_(None),
    )
    entry = (query.with_for_update() if lock else query).first()
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND)
    clinical_access(db, entry.patient_id, user, ClinicalAction.VIEW_CLINICAL_HISTORY)
    # A hidden entry does not exist for the patient (D4).
    if user.role == UserRole.PATIENT and entry.hidden_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND)
    return entry


def get_entry(db: Session, entry_id: uuid.UUID, user: User) -> ClinicalHistoryEntry:
    return _load(db, entry_id, user)


def list_revisions(db: Session, entry_id: uuid.UUID, user: User) -> list[ClinicalHistoryRevision]:
    entry = _load(db, entry_id, user)
    clinical_access(db, entry.patient_id, user, ClinicalAction.EDIT_CLINICAL_HISTORY)
    return (
        db.query(ClinicalHistoryRevision)
        .filter(ClinicalHistoryRevision.entry_id == entry.id, ClinicalHistoryRevision.clinic_id == entry.clinic_id)
        .order_by(ClinicalHistoryRevision.version)
        .all()
    )


# --- changing ---------------------------------------------------------------------------------


def _professional(db: Session, entry: ClinicalHistoryEntry, user: User) -> Staff:
    return clinical_staff(db, user, entry.patient_id, ClinicalAction.EDIT_CLINICAL_HISTORY)


def _check_version(entry: ClinicalHistoryEntry, expected: int) -> None:
    if entry.version != expected:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=STALE)


def create_entry(
    db: Session, patient_id: uuid.UUID, payload: ClinicalHistoryCreateRequest, user: User
) -> ClinicalHistoryEntry:
    if user.role == UserRole.PATIENT:
        patient = clinical_access(db, patient_id, user, ClinicalAction.DECLARE_CLINICAL_HISTORY)
        origin, staff = HistoryOrigin.PATIENT_DECLARED, None
    else:
        patient = clinical_access(db, patient_id, user, ClinicalAction.EDIT_CLINICAL_HISTORY)
        staff = clinical_staff(db, user, patient_id, ClinicalAction.EDIT_CLINICAL_HISTORY)
        origin = HistoryOrigin.PROFESSIONAL
    columns = _validated_columns(payload.category, payload.model_dump(exclude={"category"}))
    entry = ClinicalHistoryEntry(
        clinic_id=patient.clinic_id,
        patient_id=patient.id,
        category=payload.category,
        origin=origin,
        created_by_user_id=user.id,
        confirmed_by_staff_id=staff.id if staff else None,
        confirmed_at=_now() if staff else None,
        version=1,
        **columns,
    )
    db.add(entry)
    _revise(db, entry, user, HistoryChangeKind.CREATED)
    db.commit()
    db.refresh(entry)
    return entry


def update_entry(
    db: Session, entry_id: uuid.UUID, payload: ClinicalHistoryUpdateRequest, user: User
) -> tuple[ClinicalHistoryEntry, list[str]]:
    entry = _load(db, entry_id, user, lock=True)
    if user.role == UserRole.PATIENT:
        if not is_own_open_declaration(entry, user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PATIENT_LOCKED)
    else:
        _professional(db, entry, user)
    _check_version(entry, payload.expected_version)
    current = _api_values(entry)
    changes = payload.model_dump(exclude_unset=True, exclude={"expected_version"})
    merged = {**current, **changes}
    columns = _validated_columns(entry.category, merged)
    changed = sorted(field for field in changes if merged[field] != current[field])
    if not changed:
        return entry, []
    for column, value in columns.items():
        setattr(entry, column, value)
    entry.version += 1
    _revise(db, entry, user, HistoryChangeKind.UPDATED)
    db.commit()
    db.refresh(entry)
    return entry, changed


def confirm_entry(db: Session, entry_id: uuid.UUID, payload: VersionedRequest, user: User) -> ClinicalHistoryEntry:
    entry = _load(db, entry_id, user, lock=True)
    staff = _professional(db, entry, user)
    _check_version(entry, payload.expected_version)
    if entry.confirmed_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Esta entrada já está confirmada.")
    entry.confirmed_by_staff_id, entry.confirmed_at = staff.id, _now()
    entry.version += 1
    _revise(db, entry, user, HistoryChangeKind.CONFIRMED)
    db.commit()
    db.refresh(entry)
    return entry


def hide_entry(db: Session, entry_id: uuid.UUID, payload: HideRequest, user: User) -> ClinicalHistoryEntry:
    entry = _load(db, entry_id, user, lock=True)
    staff = _professional(db, entry, user)
    _check_version(entry, payload.expected_version)
    if entry.hidden_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Esta entrada já está oculta ao paciente.")
    reason = payload.reason.strip()
    if not reason:
        raise _field_errors({"reason": "Indica o motivo para ocultar."})
    entry.hidden_by_staff_id, entry.hidden_at, entry.hidden_reason = staff.id, _now(), reason
    entry.version += 1
    _revise(db, entry, user, HistoryChangeKind.HIDDEN, reason)
    db.commit()
    db.refresh(entry)
    return entry


def show_entry(db: Session, entry_id: uuid.UUID, payload: VersionedRequest, user: User) -> ClinicalHistoryEntry:
    entry = _load(db, entry_id, user, lock=True)
    _professional(db, entry, user)
    _check_version(entry, payload.expected_version)
    if entry.hidden_at is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Esta entrada já está visível para o paciente.")
    entry.hidden_by_staff_id = entry.hidden_at = entry.hidden_reason = None
    entry.version += 1
    _revise(db, entry, user, HistoryChangeKind.SHOWN)
    db.commit()
    db.refresh(entry)
    return entry


def delete_entry(db: Session, entry_id: uuid.UUID, payload: DeleteRequest, user: User) -> ClinicalHistoryEntry:
    """Soft delete: the row and its revisions stay; nobody sees the entry afterwards."""
    entry = _load(db, entry_id, user, lock=True)
    reason = (payload.reason or "").strip() or None
    if user.role == UserRole.PATIENT:
        if not is_own_open_declaration(entry, user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PATIENT_LOCKED)
    else:
        _professional(db, entry, user)
        if reason is None:
            raise _field_errors({"reason": "Indica o motivo da remoção."})
    _check_version(entry, payload.expected_version)
    entry.deleted_at, entry.deleted_by_user_id, entry.deletion_reason = _now(), user.id, reason
    entry.version += 1
    _revise(db, entry, user, HistoryChangeKind.DELETED, reason)
    db.commit()
    db.refresh(entry)
    return entry


# --- display names ----------------------------------------------------------------------------


def display_names(
    db: Session, user_ids: Iterable[uuid.UUID | None], staff_ids: Iterable[uuid.UUID | None]
) -> dict[uuid.UUID, str]:
    """Names for authors (users) and professionals (staff), in at most two queries."""
    names: dict[uuid.UUID, str] = {}
    wanted_users = {value for value in user_ids if value is not None}
    wanted_staff = {value for value in staff_ids if value is not None}
    if wanted_users:
        for user_id, full_name in db.query(User.id, User.full_name).filter(User.id.in_(wanted_users)):
            names[user_id] = full_name
    if wanted_staff:
        rows = db.query(Staff.id, User.full_name).join(User, Staff.user_id == User.id).filter(Staff.id.in_(wanted_staff))
        for staff_id, full_name in rows:
            names[staff_id] = full_name
    return names
