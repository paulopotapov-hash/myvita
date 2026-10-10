import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.audit import audit_denials, audit_request, record_access
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import AuditAction, AuditResult, ClinicalResult, ClinicalResultStatus, User
from app.modules.clinical_results.schemas import (
    ClinicalResultCorrectionRequest,
    ClinicalResultCreateRequest,
    ClinicalResultPublic,
    ClinicalResultUpdateRequest,
)
from app.modules.clinical_results.service import (
    ResultConflict,
    create_correction,
    create_result,
    get_result,
    list_results,
    release_result,
    to_public,
    update_result,
)

router = APIRouter()

_RESOURCE = "clinical_result"


def _audit(request: Request, user: User, action: AuditAction, result: ClinicalResult) -> None:
    # Identifiers and workflow state only: never the result's title, value, summary or reason.
    metadata: dict[str, object] = {"patient_id": result.patient_id, "status": result.status.value}
    if result.corrects_result_id is not None:
        metadata["corrects_result_id"] = result.corrects_result_id
    record_access(request, user, action, _RESOURCE, result.id, metadata=metadata)


@contextmanager
def _audit_refusals(request: Request, user: User, action: AuditAction, result_id: uuid.UUID) -> Iterator[None]:
    """403/404 are audited as permission denials; a refused lifecycle transition (an attempt
    to edit, release or correct a result in the wrong state) as a DENIED `action`."""
    with audit_denials(request, user, _RESOURCE, result_id):
        try:
            yield
        except ResultConflict as exc:
            audit_request(
                request,
                action=action,
                actor=user,
                result=AuditResult.DENIED,
                resource_type=_RESOURCE,
                resource_id=result_id,
                metadata={"reason": exc.reason},
            )
            raise


@router.get("/patients/{patient_id}/results", response_model=list[ClinicalResultPublic])
def list_for_patient(
    patient_id: uuid.UUID,
    request: Request,
    response: Response,
    status_filter: ClinicalResultStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list:
    with audit_denials(request, user, _RESOURCE, patient_id):
        results, total = list_results(
            db, patient_id, user, result_status=status_filter, offset=(page - 1) * page_size, limit=page_size
        )
    response.headers["X-Total-Count"] = str(total)
    record_access(
        request,
        user,
        AuditAction.CLINICAL_RESULT_VIEWED,
        "clinical_result_list",
        patient_id,
        metadata={"count": len(results)},
    )
    return to_public(db, results, user)


@router.post("/patients/{patient_id}/results", response_model=ClinicalResultPublic, status_code=201)
def create(
    patient_id: uuid.UUID,
    payload: ClinicalResultCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> object:
    with audit_denials(request, user, _RESOURCE, patient_id):
        result = create_result(db, patient_id, payload, user)
    _audit(request, user, AuditAction.CLINICAL_RESULT_CREATED, result)
    if result.status == ClinicalResultStatus.RELEASED:
        _audit(request, user, AuditAction.CLINICAL_RESULT_RELEASED, result)
    return to_public(db, [result], user)[0]


@router.get("/results/{result_id}", response_model=ClinicalResultPublic)
def detail(
    result_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> object:
    with audit_denials(request, user, _RESOURCE, result_id):
        result = get_result(db, result_id, user)
    _audit(request, user, AuditAction.CLINICAL_RESULT_VIEWED, result)
    return to_public(db, [result], user)[0]


@router.patch("/results/{result_id}", response_model=ClinicalResultPublic)
def update(
    result_id: uuid.UUID,
    payload: ClinicalResultUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> object:
    with _audit_refusals(request, user, AuditAction.CLINICAL_RESULT_DRAFT_UPDATED, result_id):
        result = update_result(db, result_id, payload, user)
    _audit(request, user, AuditAction.CLINICAL_RESULT_DRAFT_UPDATED, result)
    return to_public(db, [result], user)[0]


@router.post("/results/{result_id}/release", response_model=ClinicalResultPublic)
def release(
    result_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> object:
    with _audit_refusals(request, user, AuditAction.CLINICAL_RESULT_RELEASED, result_id):
        result = release_result(db, result_id, user)
    _audit(request, user, AuditAction.CLINICAL_RESULT_RELEASED, result)
    return to_public(db, [result], user)[0]


@router.post("/results/{result_id}/corrections", response_model=ClinicalResultPublic, status_code=201)
def correct(
    result_id: uuid.UUID,
    payload: ClinicalResultCorrectionRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> object:
    """Record a correction of a released result as a new result (the original is kept)."""
    with _audit_refusals(request, user, AuditAction.CLINICAL_RESULT_CORRECTED, result_id):
        correction = create_correction(db, result_id, payload, user)
    _audit(request, user, AuditAction.CLINICAL_RESULT_CORRECTED, correction)
    if correction.status == ClinicalResultStatus.RELEASED:
        _audit(request, user, AuditAction.CLINICAL_RESULT_RELEASED, correction)
    return to_public(db, [correction], user)[0]
