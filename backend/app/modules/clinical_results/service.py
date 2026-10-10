"""Clinical results (P2.4).

Access goes through the central clinical policy (tenant, role, active care
assignment) with the RESULTS actions, on every request: ending a professional's
care assignment ends their access immediately. On top of it, the patient
visibility rule: a patient only ever sees RELEASED results of their own record;
a draft answers exactly like a missing result (404), so its existence never leaks.

Lifecycle:
- A professional creates a DRAFT and may edit it.
- Releasing is one-way and notifies the patient in the same transaction through
  the domain-event module (generic text, deep link re-checked on open).
- A released result is never edited or deleted. A correction is a NEW result
  for the same patient that references the released one, with a mandatory
  reason; it follows the same draft -> release workflow. A result is corrected
  at most once (enforced by a unique index), so corrections form a chain and the
  professional always corrects the latest version.

Immutability is layered: these services, the ORM flush guard and the database
trigger described in app/models/clinical_result.py, plus column-level UPDATE and
no DELETE for the runtime database role. The table owner or a superuser can still
disable the trigger; that residual risk is documented there.
"""

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.clinical_access import ClinicalAction, clinical_access, clinical_staff
from app.models import ClinicalResult, ClinicalResultStatus, Document, Patient, Staff, User, UserRole
from app.modules.clinical_results.schemas import (
    ClinicalResultContent,
    ClinicalResultCorrectionRequest,
    ClinicalResultCreateRequest,
    ClinicalResultPatientView,
    ClinicalResultStaffView,
    ClinicalResultUpdateRequest,
)
from app.modules.notifications.events import NotificationEvent, NotificationTarget, TargetType, notify

_NOT_FOUND = "Resultado não encontrado."
_UNKNOWN_AUTHOR = "Profissional de saúde"
ALREADY_RELEASED = "Este resultado já foi disponibilizado ao paciente. Registe uma correção como novo resultado."
ONLY_RELEASED_CAN_BE_CORRECTED = "Só é possível corrigir um resultado disponibilizado. Edite o rascunho."
ALREADY_CORRECTED = "Este resultado já tem uma correção. Corrija a versão mais recente."


class ResultConflict(HTTPException):
    """409 on a refused lifecycle transition; `reason` is a short code for the audit trail."""

    def __init__(self, detail: str, reason: str) -> None:
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)
        self.reason = reason


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)


def _patient_only_sees_released(user: User, result: ClinicalResult) -> None:
    if user.role == UserRole.PATIENT and result.status != ClinicalResultStatus.RELEASED:
        raise _not_found()


def _check_document(db: Session, document_id: uuid.UUID | None, patient: Patient) -> None:
    """A linked document must be one of THIS patient's documents in THIS clinic."""
    if document_id is None:
        return
    document = (
        db.query(Document.id)
        .filter(
            Document.id == document_id,
            Document.clinic_id == patient.clinic_id,
            Document.patient_id == patient.id,
        )
        .first()
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="O documento indicado não pertence a este paciente.",
        )


def _release(db: Session, result: ClinicalResult, staff: Staff, patient: Patient) -> None:
    result.status = ClinicalResultStatus.RELEASED
    result.released_at = datetime.now(UTC)
    result.released_by_staff_id = staff.id
    notify(
        db,
        NotificationEvent.RESULT_CORRECTED if result.corrects_result_id else NotificationEvent.RESULT_AVAILABLE,
        clinic_id=patient.clinic_id,
        # Recipient from the result's own patient row, never from the request.
        recipient_user_id=patient.user_id,
        target=NotificationTarget(TargetType.RESULT, result.id),
        dedupe_key=str(result.id),
    )


def list_results(
    db: Session,
    patient_id: uuid.UUID,
    user: User,
    *,
    result_status: ClinicalResultStatus | None = None,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[ClinicalResult], int]:
    patient = clinical_access(db, patient_id, user, ClinicalAction.VIEW_RESULTS)
    query = db.query(ClinicalResult).filter(
        ClinicalResult.patient_id == patient.id, ClinicalResult.clinic_id == patient.clinic_id
    )
    if user.role == UserRole.PATIENT:
        query = query.filter(ClinicalResult.status == ClinicalResultStatus.RELEASED)
    if result_status is not None:
        query = query.filter(ClinicalResult.status == result_status)
    total = query.count()
    rows = (
        query.order_by(
            ClinicalResult.result_date.desc(), ClinicalResult.created_at.desc(), ClinicalResult.id.desc()
        )
        .offset(offset)
        .limit(limit)
        .all()
    )
    return rows, total


def get_result(db: Session, result_id: uuid.UUID, user: User) -> ClinicalResult:
    result = (
        db.query(ClinicalResult)
        .filter(ClinicalResult.id == result_id, ClinicalResult.clinic_id == user.clinic_id)
        .first()
    )
    if result is None:
        raise _not_found()
    try:
        clinical_access(db, result.patient_id, user, ClinicalAction.VIEW_RESULTS)
    except HTTPException as exc:
        # Another patient's result answers like a missing one (no existence oracle).
        if user.role == UserRole.PATIENT:
            raise _not_found() from None
        raise exc
    _patient_only_sees_released(user, result)
    return result


def _new_result(
    db: Session,
    patient: Patient,
    staff: Staff,
    payload: ClinicalResultContent,
    *,
    corrects: ClinicalResult | None = None,
    correction_reason: str | None = None,
) -> ClinicalResult:
    _check_document(db, payload.document_id, patient)
    result = ClinicalResult(
        clinic_id=patient.clinic_id,
        patient_id=patient.id,
        author_staff_id=staff.id,
        status=ClinicalResultStatus.DRAFT,
        corrects_result_id=corrects.id if corrects is not None else None,
        correction_reason=correction_reason,
        **payload.content_fields(),
    )
    db.add(result)
    db.flush()
    if payload.release:
        _release(db, result, staff, patient)
    db.commit()
    db.refresh(result)
    return result


def create_result(
    db: Session, patient_id: uuid.UUID, payload: ClinicalResultCreateRequest, user: User
) -> ClinicalResult:
    patient = clinical_access(db, patient_id, user, ClinicalAction.EDIT_RESULTS)
    staff = clinical_staff(db, user, patient_id, ClinicalAction.EDIT_RESULTS)
    return _new_result(db, patient, staff, payload)


def _authorized_for_edit(db: Session, result_id: uuid.UUID, user: User) -> tuple[ClinicalResult, Staff, Patient]:
    result = get_result(db, result_id, user)
    patient = clinical_access(db, result.patient_id, user, ClinicalAction.EDIT_RESULTS)
    staff = clinical_staff(db, user, result.patient_id, ClinicalAction.EDIT_RESULTS)
    # Serialize concurrent edits, releases and corrections of the same result.
    db.refresh(result, with_for_update=True)
    return result, staff, patient


def _editable(db: Session, result_id: uuid.UUID, user: User) -> tuple[ClinicalResult, Staff, Patient]:
    result, staff, patient = _authorized_for_edit(db, result_id, user)
    if result.status != ClinicalResultStatus.DRAFT:
        db.rollback()
        raise ResultConflict(ALREADY_RELEASED, "released_immutable")
    return result, staff, patient


def create_correction(
    db: Session, result_id: uuid.UUID, payload: ClinicalResultCorrectionRequest, user: User
) -> ClinicalResult:
    """Correct a released result with a new one; the original stays exactly as released."""
    original, staff, patient = _authorized_for_edit(db, result_id, user)
    if original.status != ClinicalResultStatus.RELEASED:
        db.rollback()
        raise ResultConflict(ONLY_RELEASED_CAN_BE_CORRECTED, "not_released")
    existing = db.query(ClinicalResult.id).filter(ClinicalResult.corrects_result_id == original.id).first()
    if existing is not None:
        db.rollback()
        raise ResultConflict(ALREADY_CORRECTED, "already_corrected")
    return _new_result(db, patient, staff, payload, corrects=original, correction_reason=payload.correction_reason)


def update_result(
    db: Session, result_id: uuid.UUID, payload: ClinicalResultUpdateRequest, user: User
) -> ClinicalResult:
    result, _staff, patient = _editable(db, result_id, user)
    changes = payload.model_dump(exclude_unset=True)
    if "correction_reason" in changes and result.corrects_result_id is None:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Só uma correção tem motivo de correção.",
        )
    if "document_id" in changes:
        _check_document(db, changes["document_id"], patient)
    for field, value in changes.items():
        setattr(result, field, value)
    if result.value is None and result.summary is None and result.document_id is None:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Um resultado precisa de um valor, de um resumo ou de um documento associado.",
        )
    if result.value is None and (result.unit is not None or result.reference_range is not None):
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A unidade e o intervalo de referência exigem um valor.",
        )
    db.commit()
    db.refresh(result)
    return result


def release_result(db: Session, result_id: uuid.UUID, user: User) -> ClinicalResult:
    result, staff, patient = _editable(db, result_id, user)
    _release(db, result, staff, patient)
    db.commit()
    db.refresh(result)
    return result


def _staff_names(db: Session, staff_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    """Display names for a page of rows in one query (no per-row lookups)."""
    if not staff_ids:
        return {}
    rows = db.query(Staff.id, User.full_name).join(User, User.id == Staff.user_id).filter(Staff.id.in_(staff_ids)).all()
    return {staff_id: name for staff_id, name in rows}


def _corrections_of(db: Session, results: list[ClinicalResult]) -> dict[uuid.UUID, tuple[uuid.UUID, ClinicalResultStatus]]:
    """For a page of rows, the correction of each corrected row (one query)."""
    ids = [row.id for row in results]
    if not ids:
        return {}
    rows = (
        db.query(ClinicalResult.corrects_result_id, ClinicalResult.id, ClinicalResult.status)
        .filter(ClinicalResult.corrects_result_id.in_(ids))
        .all()
    )
    return {original_id: (correction_id, correction_status) for original_id, correction_id, correction_status in rows}


def to_public(
    db: Session, results: list[ClinicalResult], user: User
) -> list[ClinicalResultStaffView | ClinicalResultPatientView]:
    """Explicit per-audience schemas: patients never get workflow or internal staff fields."""
    ids = {row.author_staff_id for row in results} | {
        row.released_by_staff_id for row in results if row.released_by_staff_id is not None
    }
    names = _staff_names(db, ids)
    corrections = _corrections_of(db, results)
    if user.role == UserRole.PATIENT:
        views: list[ClinicalResultStaffView | ClinicalResultPatientView] = []
        for row in results:
            if row.released_at is None:  # pragma: no cover - patients never receive drafts
                raise _not_found()
            correction = corrections.get(row.id)
            views.append(
                ClinicalResultPatientView(
                    id=row.id,
                    category=row.category,
                    title=row.title,
                    value=row.value,
                    unit=row.unit,
                    reference_range=row.reference_range,
                    summary=row.summary,
                    result_date=row.result_date,
                    document_id=row.document_id,
                    author_name=names.get(row.author_staff_id, _UNKNOWN_AUTHOR),
                    released_at=row.released_at,
                    # The corrected original is released (a correction needs one).
                    corrects_result_id=row.corrects_result_id,
                    # Only a released correction exists for the patient.
                    superseded_by_result_id=(
                        correction[0]
                        if correction is not None and correction[1] == ClinicalResultStatus.RELEASED
                        else None
                    ),
                )
            )
        return views
    staff_views: list[ClinicalResultStaffView | ClinicalResultPatientView] = []
    for row in results:
        correction = corrections.get(row.id)
        staff_views.append(
            ClinicalResultStaffView(
                id=row.id,
                patient_id=row.patient_id,
                category=row.category,
                title=row.title,
                value=row.value,
                unit=row.unit,
                reference_range=row.reference_range,
                summary=row.summary,
                result_date=row.result_date,
                document_id=row.document_id,
                status=row.status,
                author_name=names.get(row.author_staff_id, _UNKNOWN_AUTHOR),
                released_at=row.released_at,
                released_by_name=(
                    names.get(row.released_by_staff_id, _UNKNOWN_AUTHOR) if row.released_by_staff_id else None
                ),
                corrects_result_id=row.corrects_result_id,
                correction_reason=row.correction_reason,
                corrected_by_result_id=correction[0] if correction is not None else None,
                superseded=correction is not None and correction[1] == ClinicalResultStatus.RELEASED,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
        )
    return staff_views
