import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.audit import client_ip, record_audit_event
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import AuditAction, AuditResult, Consent, User
from app.modules.consents.schemas import ConsentCreateRequest, ConsentPublic
from app.modules.consents.service import get_consent, grant_consent, list_consents, revoke_consent

router = APIRouter()


def _audit(request: Request, user: User, action: AuditAction, consent: Consent) -> None:
    record_audit_event(
        action=action,
        result=AuditResult.SUCCESS,
        clinic_id=user.clinic_id,
        actor_user_id=user.id,
        actor_email=user.email,
        resource_type="consent",
        resource_id=consent.id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


@router.get("/patients/{patient_id}/consents", response_model=list[ConsentPublic])
def list_patient_consents(
    patient_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Consent]:
    consents = list_consents(db, patient_id, user)
    record_audit_event(
        action=AuditAction.CONSENT_VIEWED,
        result=AuditResult.SUCCESS,
        clinic_id=user.clinic_id,
        actor_user_id=user.id,
        actor_email=user.email,
        resource_type="consent_list",
        resource_id=patient_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        metadata={"count": len(consents)},
    )
    return consents


@router.post("/patients/{patient_id}/consents", response_model=ConsentPublic, status_code=201)
def create_consent(
    patient_id: uuid.UUID,
    payload: ConsentCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Consent:
    consent = grant_consent(db, patient_id, payload, user)
    _audit(request, user, AuditAction.CONSENT_GRANTED, consent)
    return consent


@router.get("/consents/{consent_id}", response_model=ConsentPublic)
def consent_detail(
    consent_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Consent:
    consent = get_consent(db, consent_id, user)
    _audit(request, user, AuditAction.CONSENT_VIEWED, consent)
    return consent


@router.post("/consents/{consent_id}/revoke", response_model=ConsentPublic)
def revoke(
    consent_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Consent:
    consent = revoke_consent(db, consent_id, user)
    _audit(request, user, AuditAction.CONSENT_REVOKED, consent)
    return consent
