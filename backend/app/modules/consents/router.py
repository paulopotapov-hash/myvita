import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.audit import audit_denials, record_access
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import AuditAction, Consent, User
from app.modules.consents.schemas import ConsentCreateRequest, ConsentPublic
from app.modules.consents.service import get_consent, grant_consent, list_consents, revoke_consent

router = APIRouter()


def _audit(request: Request, user: User, action: AuditAction, consent: Consent) -> None:
    record_access(request, user, action, "consent", consent.id)


@router.get("/patients/{patient_id}/consents", response_model=list[ConsentPublic])
def list_patient_consents(
    patient_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Consent]:
    with audit_denials(request, user, "consent", patient_id):
        consents = list_consents(db, patient_id, user)
    record_access(
        request, user, AuditAction.CONSENT_VIEWED, "consent_list", patient_id, metadata={"count": len(consents)}
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
    with audit_denials(request, user, "consent", patient_id):
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
    with audit_denials(request, user, "consent", consent_id):
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
    with audit_denials(request, user, "consent", consent_id):
        consent = revoke_consent(db, consent_id, user)
    _audit(request, user, AuditAction.CONSENT_REVOKED, consent)
    return consent
