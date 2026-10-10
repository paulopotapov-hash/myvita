import uuid
from collections.abc import Iterable

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.audit import audit_denials, record_access
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import AuditAction, MedicalRecord, MedicalRecordVisibility, Staff, User, UserRole
from app.modules.medical_records.schemas import (
    MedicalRecordCreateRequest,
    MedicalRecordOut,
    MedicalRecordPatientView,
    MedicalRecordPublic,
    MedicalRecordRevisionPublic,
    MedicalRecordUpdateRequest,
    MedicalRecordVisibilityRequest,
)
from app.modules.medical_records.service import (
    create_record,
    get_record,
    list_records,
    list_revisions,
    share_record,
    unshare_record,
    update_record,
)

router = APIRouter()

_UNKNOWN_AUTHOR = "Profissional de saúde"


def _staff_names(db: Session, staff_ids: Iterable[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    """Display names for a page of rows in one query (no per-row lookups)."""
    ids = {staff_id for staff_id in staff_ids if staff_id is not None}
    if not ids:
        return {}
    rows = db.query(Staff.id, User.full_name).join(User, User.id == Staff.user_id).filter(Staff.id.in_(ids)).all()
    return {staff_id: name for staff_id, name in rows}


def _records_public(
    db: Session, records: list[MedicalRecord], user: User
) -> list[MedicalRecordPublic | MedicalRecordPatientView]:
    """Explicit per-audience schemas (P2.5): patients never get staff ids, versions or sharing metadata."""
    if user.role == UserRole.PATIENT:
        names = _staff_names(db, [record.author_staff_id for record in records])
        return [
            MedicalRecordPatientView(
                id=record.id,
                author_name=names.get(record.author_staff_id, _UNKNOWN_AUTHOR),
                title=record.title,
                content=record.content,
                created_at=record.created_at,
                updated_at=record.updated_at,
            )
            for record in records
        ]
    names = _staff_names(
        db,
        [record.author_staff_id for record in records]
        + [record.visibility_changed_by_staff_id for record in records if record.visibility_changed_by_staff_id],
    )
    return [
        MedicalRecordPublic(
            id=record.id,
            clinic_id=record.clinic_id,
            patient_id=record.patient_id,
            author_staff_id=record.author_staff_id,
            author_name=names.get(record.author_staff_id, _UNKNOWN_AUTHOR),
            title=record.title,
            content=record.content,
            visibility=record.patient_visibility,
            visibility_changed_at=record.visibility_changed_at,
            visibility_changed_by_name=(
                names.get(record.visibility_changed_by_staff_id, _UNKNOWN_AUTHOR)
                if record.visibility_changed_by_staff_id is not None
                else None
            ),
            version=record.version,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
        for record in records
    ]


def _audit(
    request: Request,
    user: User,
    action: AuditAction,
    record: MedicalRecord,
    *,
    previous: MedicalRecordVisibility | None = None,
) -> None:
    # Identifiers and visibility codes only: never the record's title or content.
    metadata: dict[str, object] = {"patient_id": record.patient_id, "visibility": record.patient_visibility.value}
    if previous is not None:
        metadata["from"] = previous.value
        metadata["to"] = record.patient_visibility.value
    record_access(request, user, action, "medical_record", record.id, metadata=metadata)


@router.get("/patients/{patient_id}/medical-records", response_model=list[MedicalRecordOut])
def list_for_patient(
    patient_id: uuid.UUID,
    request: Request,
    response: Response,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[MedicalRecordPublic | MedicalRecordPatientView]:
    with audit_denials(request, user, "medical_record", patient_id):
        records, total = list_records(db, patient_id, user, offset=(page - 1) * page_size, limit=page_size)
    response.headers["X-Total-Count"] = str(total)
    record_access(
        request, user, AuditAction.MEDICAL_RECORD_VIEWED, "medical_record_list", patient_id, metadata={"count": len(records)}
    )
    return _records_public(db, records, user)


@router.post("/patients/{patient_id}/medical-records", response_model=MedicalRecordOut, status_code=201)
def create(
    patient_id: uuid.UUID,
    payload: MedicalRecordCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MedicalRecordPublic | MedicalRecordPatientView:
    with audit_denials(request, user, "medical_record", patient_id):
        record = create_record(db, patient_id, payload, user)
    _audit(request, user, AuditAction.MEDICAL_RECORD_CREATED, record)
    if record.patient_visibility == MedicalRecordVisibility.SHARED:
        _audit(request, user, AuditAction.MEDICAL_RECORD_SHARED, record, previous=MedicalRecordVisibility.INTERNAL)
    return _records_public(db, [record], user)[0]


@router.get("/medical-records/{record_id}", response_model=MedicalRecordOut)
def detail(
    record_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MedicalRecordPublic | MedicalRecordPatientView:
    with audit_denials(request, user, "medical_record", record_id):
        record = get_record(db, record_id, user)
    _audit(request, user, AuditAction.MEDICAL_RECORD_VIEWED, record)
    return _records_public(db, [record], user)[0]


@router.patch("/medical-records/{record_id}", response_model=MedicalRecordOut)
def update(
    record_id: uuid.UUID,
    payload: MedicalRecordUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MedicalRecordPublic | MedicalRecordPatientView:
    with audit_denials(request, user, "medical_record", record_id):
        record = update_record(db, record_id, payload, user)
    _audit(request, user, AuditAction.MEDICAL_RECORD_UPDATED, record)
    return _records_public(db, [record], user)[0]


@router.post("/medical-records/{record_id}/share", response_model=MedicalRecordOut)
def share(
    record_id: uuid.UUID,
    payload: MedicalRecordVisibilityRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MedicalRecordPublic | MedicalRecordPatientView:
    with audit_denials(request, user, "medical_record", record_id):
        record, previous = share_record(db, record_id, payload.expected_version, user)
    if previous is not None:
        _audit(request, user, AuditAction.MEDICAL_RECORD_SHARED, record, previous=previous)
    return _records_public(db, [record], user)[0]


@router.post("/medical-records/{record_id}/unshare", response_model=MedicalRecordOut)
def unshare(
    record_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MedicalRecordPublic | MedicalRecordPatientView:
    with audit_denials(request, user, "medical_record", record_id):
        record, previous = unshare_record(db, record_id, user)
    if previous is not None:
        _audit(request, user, AuditAction.MEDICAL_RECORD_UNSHARED, record, previous=previous)
    return _records_public(db, [record], user)[0]


@router.get("/medical-records/{record_id}/revisions", response_model=list[MedicalRecordRevisionPublic])
def revisions(
    record_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[MedicalRecordRevisionPublic]:
    with audit_denials(request, user, "medical_record", record_id):
        record, rows = list_revisions(db, record_id, user)
    _audit(request, user, AuditAction.MEDICAL_RECORD_VIEWED, record)
    names = _staff_names(db, [row.editor_staff_id for row in rows])
    return [
        MedicalRecordRevisionPublic(
            id=row.id,
            record_id=row.record_id,
            editor_staff_id=row.editor_staff_id,
            editor_name=names.get(row.editor_staff_id, _UNKNOWN_AUTHOR),
            version=row.version,
            title=row.title,
            content=row.content,
            visibility=row.patient_visibility,
            created_at=row.created_at,
        )
        for row in rows
    ]
