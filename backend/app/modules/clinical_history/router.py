import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.core.audit import record_access, record_denied_access
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import AuditAction, ClinicalHistoryEntry, HistoryCategory, User, UserRole
from app.modules.clinical_history import service
from app.modules.clinical_history.schemas import (
    ClinicalHistoryCreateRequest,
    ClinicalHistoryOut,
    ClinicalHistoryPatientView,
    ClinicalHistoryRevisionOut,
    ClinicalHistoryStaffView,
    ClinicalHistoryUpdateRequest,
    DeleteRequest,
    HideRequest,
    VersionedRequest,
)

router = APIRouter()
View = ClinicalHistoryStaffView | ClinicalHistoryPatientView


def _views(db: Session, entries: list[ClinicalHistoryEntry], user: User) -> list[View]:
    """Per-audience schemas, built field by field: patients never get staff ids or hiding details."""
    names = service.display_names(
        db,
        (entry.created_by_user_id for entry in entries),
        [staff_id for entry in entries for staff_id in (entry.confirmed_by_staff_id, entry.hidden_by_staff_id)],
    )
    views: list[View] = []
    for entry in entries:
        common = {
            "id": entry.id,
            "category": entry.category,
            **service._api_values(entry),
            "origin": entry.origin,
            "confirmed": entry.confirmed_at is not None,
            "confirmed_at": entry.confirmed_at,
            "confirmed_by_name": names.get(entry.confirmed_by_staff_id) if entry.confirmed_by_staff_id else None,
            "version": entry.version,
            "created_at": entry.created_at,
            "updated_at": entry.updated_at,
        }
        if user.role == UserRole.PATIENT:
            views.append(ClinicalHistoryPatientView(**common, can_edit=service.is_own_open_declaration(entry, user)))
        else:
            views.append(
                ClinicalHistoryStaffView(
                    **common,
                    created_by_name=names.get(entry.created_by_user_id, "—"),
                    hidden=entry.hidden_at is not None,
                    hidden_at=entry.hidden_at,
                    hidden_reason=entry.hidden_reason,
                    hidden_by_name=names.get(entry.hidden_by_staff_id) if entry.hidden_by_staff_id else None,
                )
            )
    return views


def _audit(
    request: Request, user: User, action: AuditAction, entry: ClinicalHistoryEntry, fields: list[str] | None = None
) -> None:
    # Identifiers, the category code and changed field names only: never names, dates, notes or reasons.
    metadata: dict[str, object] = {"patient_id": entry.patient_id, "category": entry.category}
    if fields is not None:
        metadata["fields"] = fields
    record_access(request, user, action, "clinical_history_entry", entry.id, metadata=metadata)


@contextmanager
def _denials(request: Request, user: User, resource_id: uuid.UUID) -> Iterator[None]:
    try:
        yield
    except HTTPException as exc:
        if exc.status_code in {403, 404}:
            record_denied_access(request, user, "clinical_history_entry", resource_id)
        raise


@router.get("/patients/{patient_id}/clinical-history", response_model=list[ClinicalHistoryOut])
def list_for_patient(
    patient_id: uuid.UUID,
    request: Request,
    category: HistoryCategory | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[View]:
    with _denials(request, user, patient_id):
        entries = service.list_entries(db, patient_id, user, category)
    record_access(
        request,
        user,
        AuditAction.CLINICAL_HISTORY_VIEWED,
        "clinical_history_list",
        patient_id,
        metadata={"count": len(entries), **({"category": category} if category else {})},
    )
    return _views(db, entries, user)


@router.post("/patients/{patient_id}/clinical-history", response_model=ClinicalHistoryOut, status_code=201)
def create(
    patient_id: uuid.UUID,
    payload: ClinicalHistoryCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> View:
    with _denials(request, user, patient_id):
        entry = service.create_entry(db, patient_id, payload, user)
    action = AuditAction.CLINICAL_HISTORY_DECLARED if user.role == UserRole.PATIENT else AuditAction.CLINICAL_HISTORY_CREATED
    _audit(request, user, action, entry)
    return _views(db, [entry], user)[0]


@router.get("/clinical-history/{entry_id}", response_model=ClinicalHistoryOut)
def detail(
    entry_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> View:
    with _denials(request, user, entry_id):
        entry = service.get_entry(db, entry_id, user)
    _audit(request, user, AuditAction.CLINICAL_HISTORY_VIEWED, entry)
    return _views(db, [entry], user)[0]


@router.patch("/clinical-history/{entry_id}", response_model=ClinicalHistoryOut)
def update(
    entry_id: uuid.UUID,
    payload: ClinicalHistoryUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> View:
    with _denials(request, user, entry_id):
        entry, changed = service.update_entry(db, entry_id, payload, user)
    if changed:
        _audit(request, user, AuditAction.CLINICAL_HISTORY_UPDATED, entry, changed)
    return _views(db, [entry], user)[0]


def _apply(
    action: AuditAction,
    operation: Callable[..., ClinicalHistoryEntry],
    entry_id: uuid.UUID,
    payload: VersionedRequest,
    request: Request,
    db: Session,
    user: User,
) -> View:
    """Confirm / hide / show / delete: run the service operation, audit it, answer per audience."""
    with _denials(request, user, entry_id):
        entry = operation(db, entry_id, payload, user)
    _audit(request, user, action, entry)
    return _views(db, [entry], user)[0]


@router.post("/clinical-history/{entry_id}/confirm", response_model=ClinicalHistoryOut)
def confirm(
    entry_id: uuid.UUID,
    payload: VersionedRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> View:
    return _apply(AuditAction.CLINICAL_HISTORY_CONFIRMED, service.confirm_entry, entry_id, payload, request, db, user)


@router.post("/clinical-history/{entry_id}/hide", response_model=ClinicalHistoryOut)
def hide(
    entry_id: uuid.UUID,
    payload: HideRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> View:
    return _apply(AuditAction.CLINICAL_HISTORY_HIDDEN, service.hide_entry, entry_id, payload, request, db, user)


@router.post("/clinical-history/{entry_id}/show", response_model=ClinicalHistoryOut)
def show(
    entry_id: uuid.UUID,
    payload: VersionedRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> View:
    return _apply(AuditAction.CLINICAL_HISTORY_SHOWN, service.show_entry, entry_id, payload, request, db, user)


@router.post("/clinical-history/{entry_id}/delete", response_model=ClinicalHistoryOut)
def delete(
    entry_id: uuid.UUID,
    payload: DeleteRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> View:
    return _apply(AuditAction.CLINICAL_HISTORY_DELETED, service.delete_entry, entry_id, payload, request, db, user)


@router.get("/clinical-history/{entry_id}/revisions", response_model=list[ClinicalHistoryRevisionOut])
def revisions(
    entry_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ClinicalHistoryRevisionOut]:
    with _denials(request, user, entry_id):
        rows = service.list_revisions(db, entry_id, user)
    names = service.display_names(db, (row.changed_by_user_id for row in rows), ())
    return [
        ClinicalHistoryRevisionOut(
            version=row.version,
            change_kind=row.change_kind,
            changed_by_name=names.get(row.changed_by_user_id, "—"),
            change_reason=row.change_reason,
            snapshot=row.snapshot,
            created_at=row.created_at,
        )
        for row in rows
    ]
