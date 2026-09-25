import uuid
from typing import Never

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.audit import client_ip, record_audit_event
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import AuditAction, AuditResult, Medication, MedicationStatus, User
from app.modules.medications.schemas import (
    MedicationCreateRequest,
    MedicationDeactivateRequest,
    MedicationPublic,
    MedicationUpdateRequest,
)
from app.modules.medications.service import (
    create_medication,
    deactivate_medication,
    get_medication,
    list_medications,
    update_medication,
)

router = APIRouter()


def _audit(request: Request, user: User, action: AuditAction, medication: Medication) -> None:
    record_audit_event(
        action=action,
        result=AuditResult.SUCCESS,
        clinic_id=user.clinic_id,
        actor_user_id=user.id,
        actor_email=user.email,
        resource_type="medication",
        resource_id=medication.id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


def _audit_denied(request: Request, user: User, resource_id: uuid.UUID) -> None:
    record_audit_event(
        action=AuditAction.PERMISSION_DENIED,
        result=AuditResult.DENIED,
        clinic_id=user.clinic_id,
        actor_user_id=user.id,
        actor_email=user.email,
        resource_type="medication",
        resource_id=resource_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        metadata={"path": request.url.path},
    )


def _audit_and_raise(request: Request, user: User, resource_id: uuid.UUID, exc: HTTPException) -> Never:
    if exc.status_code in {403, 404}:
        _audit_denied(request, user, resource_id)
    raise exc


@router.get("/patients/{patient_id}/medications", response_model=list[MedicationPublic])
def list_for_patient(
    patient_id: uuid.UUID,
    request: Request,
    response: Response,
    status_filter: MedicationStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Medication]:
    try:
        medications, total = list_medications(
            db,
            patient_id,
            user,
            medication_status=status_filter,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
    except HTTPException as exc:
        _audit_and_raise(request, user, patient_id, exc)
    response.headers["X-Total-Count"] = str(total)
    record_audit_event(
        action=AuditAction.MEDICATION_VIEWED,
        result=AuditResult.SUCCESS,
        clinic_id=user.clinic_id,
        actor_user_id=user.id,
        actor_email=user.email,
        resource_type="medication_list",
        resource_id=patient_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        metadata={"count": len(medications)},
    )
    return medications


@router.post("/patients/{patient_id}/medications", response_model=MedicationPublic, status_code=201)
def create(
    patient_id: uuid.UUID,
    payload: MedicationCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Medication:
    try:
        medication = create_medication(db, patient_id, payload, user)
    except HTTPException as exc:
        _audit_and_raise(request, user, patient_id, exc)
    _audit(request, user, AuditAction.MEDICATION_CREATED, medication)
    return medication


@router.get("/medications/{medication_id}", response_model=MedicationPublic)
def detail(
    medication_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Medication:
    try:
        medication = get_medication(db, medication_id, user)
    except HTTPException as exc:
        _audit_and_raise(request, user, medication_id, exc)
    _audit(request, user, AuditAction.MEDICATION_VIEWED, medication)
    return medication


@router.patch("/medications/{medication_id}", response_model=MedicationPublic)
def update(
    medication_id: uuid.UUID,
    payload: MedicationUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Medication:
    try:
        medication = update_medication(db, medication_id, payload, user)
    except HTTPException as exc:
        _audit_and_raise(request, user, medication_id, exc)
    action = (
        AuditAction.MEDICATION_DEACTIVATED
        if medication.status != MedicationStatus.ACTIVE
        else AuditAction.MEDICATION_UPDATED
    )
    _audit(request, user, action, medication)
    return medication


@router.post("/medications/{medication_id}/deactivate", response_model=MedicationPublic)
def deactivate(
    medication_id: uuid.UUID,
    request: Request,
    payload: MedicationDeactivateRequest | None = Body(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Medication:
    try:
        medication = deactivate_medication(db, medication_id, payload, user)
    except HTTPException as exc:
        _audit_and_raise(request, user, medication_id, exc)
    _audit(request, user, AuditAction.MEDICATION_DEACTIVATED, medication)
    return medication
