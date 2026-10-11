import uuid
from typing import Never

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.audit import record_access, record_denied_access
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import AuditAction, Medication, MedicationStatus, User, UserRole
from app.modules.medications import service
from app.modules.medications.schemas import (
    MedicationConfirmRequest,
    MedicationCreateRequest,
    MedicationDeactivateRequest,
    MedicationDeleteRequest,
    MedicationHideRequest,
    MedicationOut,
    MedicationPatientView,
    MedicationPublic,
    MedicationUpdateRequest,
)

router = APIRouter()
View = MedicationPublic | MedicationPatientView


def _for_audience(medication: Medication, user: User) -> View:
    """Explicit per-audience schemas, built field by field: patients never receive internal
    clinic or staff identifiers, nor anything about hiding (hidden medication is never sent)."""
    common = {
        "id": medication.id,
        "name": medication.name,
        "dosage": medication.dosage,
        "route": medication.route,
        "frequency": medication.frequency,
        "instructions": medication.instructions,
        "status": medication.status,
        "start_date": medication.start_date,
        "end_date": medication.end_date,
        "origin": medication.origin,
        "confirmed": medication.confirmed_at is not None,
        "created_at": medication.created_at,
        "updated_at": medication.updated_at,
    }
    if user.role == UserRole.PATIENT:
        return MedicationPatientView(**common, can_edit=service.is_own_open_declaration(medication, user))
    return MedicationPublic(
        **common,
        clinic_id=medication.clinic_id,
        patient_id=medication.patient_id,
        prescribed_by_staff_id=medication.prescribed_by_staff_id,
        confirmed_at=medication.confirmed_at,
        confirmed_by_staff_id=medication.confirmed_by_staff_id,
        hidden=medication.hidden_at is not None,
        hidden_at=medication.hidden_at,
        hidden_reason=medication.hidden_reason,
    )


def _audit(request: Request, user: User, action: AuditAction, medication: Medication) -> None:
    record_access(request, user, action, "medication", medication.id, metadata={"patient_id": medication.patient_id})


def _audit_and_raise(request: Request, user: User, resource_id: uuid.UUID, exc: HTTPException) -> Never:
    if exc.status_code in {403, 404}:
        record_denied_access(request, user, "medication", resource_id)
    raise exc


@router.get("/patients/{patient_id}/medications", response_model=list[MedicationOut])
def list_for_patient(
    patient_id: uuid.UUID,
    request: Request,
    response: Response,
    status_filter: MedicationStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[View]:
    try:
        medications, total = service.list_medications(
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
    record_access(
        request, user, AuditAction.MEDICATION_VIEWED, "medication_list", patient_id, metadata={"count": len(medications)}
    )
    return [_for_audience(medication, user) for medication in medications]


@router.post("/patients/{patient_id}/medications", response_model=MedicationOut, status_code=201)
def create(
    patient_id: uuid.UUID,
    payload: MedicationCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> View:
    try:
        medication = service.create_medication(db, patient_id, payload, user)
    except HTTPException as exc:
        _audit_and_raise(request, user, patient_id, exc)
    action = AuditAction.MEDICATION_DECLARED if user.role == UserRole.PATIENT else AuditAction.MEDICATION_CREATED
    _audit(request, user, action, medication)
    return _for_audience(medication, user)


@router.get("/medications/{medication_id}", response_model=MedicationOut)
def detail(
    medication_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> View:
    try:
        medication = service.get_medication(db, medication_id, user)
    except HTTPException as exc:
        _audit_and_raise(request, user, medication_id, exc)
    _audit(request, user, AuditAction.MEDICATION_VIEWED, medication)
    return _for_audience(medication, user)


@router.patch("/medications/{medication_id}", response_model=MedicationOut)
def update(
    medication_id: uuid.UUID,
    payload: MedicationUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> View:
    try:
        medication = service.update_medication(db, medication_id, payload, user)
    except HTTPException as exc:
        _audit_and_raise(request, user, medication_id, exc)
    action = (
        AuditAction.MEDICATION_DEACTIVATED
        if medication.status != MedicationStatus.ACTIVE
        else AuditAction.MEDICATION_UPDATED
    )
    _audit(request, user, action, medication)
    return _for_audience(medication, user)


@router.post("/medications/{medication_id}/deactivate", response_model=MedicationOut)
def deactivate(
    medication_id: uuid.UUID,
    request: Request,
    payload: MedicationDeactivateRequest | None = Body(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> View:
    try:
        medication = service.deactivate_medication(db, medication_id, payload, user)
    except HTTPException as exc:
        _audit_and_raise(request, user, medication_id, exc)
    _audit(request, user, AuditAction.MEDICATION_DEACTIVATED, medication)
    return _for_audience(medication, user)


@router.post("/medications/{medication_id}/confirm", response_model=MedicationOut)
def confirm(
    medication_id: uuid.UUID,
    request: Request,
    payload: MedicationConfirmRequest | None = Body(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> View:
    try:
        medication = service.confirm_medication(db, medication_id, payload or MedicationConfirmRequest(), user)
    except HTTPException as exc:
        _audit_and_raise(request, user, medication_id, exc)
    _audit(request, user, AuditAction.MEDICATION_CONFIRMED, medication)
    return _for_audience(medication, user)


@router.post("/medications/{medication_id}/hide", response_model=MedicationOut)
def hide(
    medication_id: uuid.UUID,
    payload: MedicationHideRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> View:
    try:
        medication = service.hide_medication(db, medication_id, payload, user)
    except HTTPException as exc:
        _audit_and_raise(request, user, medication_id, exc)
    _audit(request, user, AuditAction.MEDICATION_HIDDEN, medication)
    return _for_audience(medication, user)


@router.post("/medications/{medication_id}/show", response_model=MedicationOut)
def show(
    medication_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> View:
    try:
        medication = service.show_medication(db, medication_id, user)
    except HTTPException as exc:
        _audit_and_raise(request, user, medication_id, exc)
    _audit(request, user, AuditAction.MEDICATION_SHOWN, medication)
    return _for_audience(medication, user)


@router.post("/medications/{medication_id}/delete", response_model=MedicationOut)
def delete(
    medication_id: uuid.UUID,
    request: Request,
    payload: MedicationDeleteRequest | None = Body(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> View:
    try:
        medication = service.delete_medication(db, medication_id, payload or MedicationDeleteRequest(), user)
    except HTTPException as exc:
        _audit_and_raise(request, user, medication_id, exc)
    _audit(request, user, AuditAction.MEDICATION_DELETED, medication)
    return _for_audience(medication, user)
