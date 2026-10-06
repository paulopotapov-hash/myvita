import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.audit import client_ip, record_audit_event
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import AuditAction, AuditResult, Medication, User
from app.modules.medications.schemas import MedicationCreateRequest, MedicationPublic, MedicationUpdateRequest
from app.modules.medications.service import (
    create_medication,
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


@router.get("/patients/{patient_id}/medications", response_model=list[MedicationPublic])
def list_for_patient(
    patient_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Medication]:
    medications = list_medications(db, patient_id, user)
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
    medication = create_medication(db, patient_id, payload, user)
    _audit(request, user, AuditAction.MEDICATION_CREATED, medication)
    return medication


@router.get("/medications/{medication_id}", response_model=MedicationPublic)
def detail(
    medication_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Medication:
    medication = get_medication(db, medication_id, user)
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
    medication = update_medication(db, medication_id, payload, user)
    _audit(request, user, AuditAction.MEDICATION_UPDATED, medication)
    return medication
