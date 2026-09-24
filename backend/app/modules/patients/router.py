import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.core.audit import client_ip, record_audit_event
from app.core.database import get_db
from app.core.pagination import DEFAULT_PAGE_SIZE, Limit, Offset
from app.core.rate_limit import REGISTRATION_RATE_LIMIT, limiter
from app.core.security import (
    ClinicalPermission,
    get_current_clinic_id,
    get_current_user,
    has_permission,
    require_permission,
    set_session_cookie,
)
from app.models import AuditAction, AuditResult, Patient, User, UserRole
from app.modules.patients.schemas import PatientPublic, PatientRegisterRequest, PatientUpdateRequest
from app.modules.patients.service import list_patients_for_clinic, register_patient

router = APIRouter()

# See app/modules/appointments/router.py for why this is a module-level
# variable instead of an inline require_roles(...) call in the signature.
_patient_read = require_permission(ClinicalPermission.PATIENT_DIRECTORY_READ)
_patient_update = require_permission(ClinicalPermission.PATIENT_UPDATE)


@router.post("/register", response_model=PatientPublic, status_code=201)
@limiter.limit(REGISTRATION_RATE_LIMIT)
def register(
    request: Request, payload: PatientRegisterRequest, response: Response, db: Session = Depends(get_db)
) -> PatientPublic:
    patient, user = register_patient(db, payload)
    set_session_cookie(response, user)  # auto-login after successful registration
    record_audit_event(
        action=AuditAction.PATIENT_CREATED,
        result=AuditResult.SUCCESS,
        clinic_id=patient.clinic_id,
        actor_user_id=user.id,
        actor_email=user.email,
        resource_type="patient",
        resource_id=patient.id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return PatientPublic(
        id=patient.id,
        clinic_id=patient.clinic_id,
        full_name=user.full_name,
        birth_date=patient.birth_date,
        phone=patient.phone,
        national_health_number=patient.national_health_number,
        is_active=user.is_active,
        created_at=patient.created_at,
        updated_at=patient.updated_at,
    )


@router.get("", response_model=list[PatientPublic])
def list_mine(
    request: Request,
    limit: Limit = DEFAULT_PAGE_SIZE,
    offset: Offset = 0,
    db: Session = Depends(get_db),
    clinic_id: str = Depends(get_current_clinic_id),
    staff_user: User = Depends(_patient_read),
) -> list[PatientPublic]:
    """
    Patient directory for the caller's own clinic — needed so staff can
    pick a patient when creating an appointment, and so appointment lists
    can show a name instead of a bare UUID. Never a cross-clinic listing:
    clinic_id always comes from the staff member's own session.
    """
    patients = list_patients_for_clinic(db, clinic_id, limit, offset)
    record_audit_event(
        action=AuditAction.STAFF_VIEWED_PATIENT,
        result=AuditResult.SUCCESS,
        clinic_id=clinic_id,
        actor_user_id=staff_user.id,
        actor_email=staff_user.email,
        resource_type="patient_list",
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        metadata={"count": len(patients)},
    )
    return [
        PatientPublic(
            id=p.id,
            clinic_id=p.clinic_id,
            full_name=p.user.full_name,
            birth_date=p.birth_date,
            phone=p.phone,
            national_health_number=p.national_health_number,
            is_active=p.user.is_active,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p in patients
    ]


def _visible_patient(db: Session, patient_id: uuid.UUID, user: User) -> Patient:
    patient = db.query(Patient).filter(Patient.id == patient_id, Patient.clinic_id == user.clinic_id).first()
    if patient is None or (user.role == UserRole.PATIENT and patient.user_id != user.id):
        raise HTTPException(status_code=404, detail="Paciente não encontrado.")
    return patient


def _public(patient: Patient) -> PatientPublic:
    return PatientPublic(
        id=patient.id,
        clinic_id=patient.clinic_id,
        full_name=patient.user.full_name,
        birth_date=patient.birth_date,
        phone=patient.phone,
        national_health_number=patient.national_health_number,
        is_active=patient.user.is_active,
        created_at=patient.created_at,
        updated_at=patient.updated_at,
    )


@router.get("/{patient_id}", response_model=PatientPublic)
def detail(
    patient_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PatientPublic:
    patient = _visible_patient(db, patient_id, user)
    if user.role != UserRole.PATIENT and not has_permission(
        user, ClinicalPermission.PATIENT_DIRECTORY_READ
    ):
        record_audit_event(
            action=AuditAction.PERMISSION_DENIED,
            result=AuditResult.DENIED,
            clinic_id=user.clinic_id,
            actor_user_id=user.id,
            actor_email=user.email,
            ip_address=client_ip(request),
            user_agent=request.headers.get("user-agent"),
            metadata={"path": request.url.path, "required_permission": "patient_directory.read"},
        )
        raise HTTPException(status_code=403, detail="Sem permissões para aceder a este recurso.")
    record_audit_event(
        action=AuditAction.STAFF_VIEWED_PATIENT
        if user.role != UserRole.PATIENT
        else AuditAction.PATIENT_VIEWED_OWN_RECORD,
        result=AuditResult.SUCCESS,
        clinic_id=user.clinic_id,
        actor_user_id=user.id,
        actor_email=user.email,
        resource_type="patient",
        resource_id=patient.id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return _public(patient)


@router.patch("/{patient_id}", response_model=PatientPublic)
def update(
    patient_id: uuid.UUID,
    payload: PatientUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(_patient_update),
) -> PatientPublic:
    patient = _visible_patient(db, patient_id, user)
    values = payload.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=422, detail="Indique pelo menos um campo para alterar.")
    if "full_name" in values and values["full_name"] is None:
        raise HTTPException(status_code=422, detail="Nome obrigatório.")
    full_name = values.pop("full_name", patient.user.full_name)
    changed_values = {key: value for key, value in values.items() if getattr(patient, key) != value}
    name_changed = full_name != patient.user.full_name
    if not name_changed and not changed_values:
        return _public(patient)
    if name_changed:
        patient.user.full_name = full_name
    for key, value in changed_values.items():
        setattr(patient, key, value)
    patient.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(patient)
    record_audit_event(
        action=AuditAction.PATIENT_UPDATED,
        result=AuditResult.SUCCESS,
        clinic_id=user.clinic_id,
        actor_user_id=user.id,
        actor_email=user.email,
        resource_type="patient",
        resource_id=patient.id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return _public(patient)
