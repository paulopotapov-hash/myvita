import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.audit import audit_request
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import AuditAction, Consent, User
from app.modules.consents.schemas import ConsentCreateRequest, ConsentPublic
from app.modules.consents.service import get_consent, grant_consent, list_consents, revoke_consent

router = APIRouter()


def _audit(request: Request, user: User, action: AuditAction, consent: Consent) -> None:
    audit_request(request, action=action, actor=user, resource_type="consent", resource_id=consent.id)


@router.get("/patients/{patient_id}/consents", response_model=list[ConsentPublic])
def list_patient_consents(
    patient_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Consent]:
    consents = list_consents(db, patient_id, user)
    audit_request(
        request,
        action=AuditAction.CONSENT_VIEWED,
        actor=user,
        resource_type="consent_list",
        resource_id=patient_id,
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
