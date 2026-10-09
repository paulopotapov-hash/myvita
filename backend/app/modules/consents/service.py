import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clinical_access import ClinicalAction, clinical_access
from app.models import Consent, ConsentStatus, Patient, User, UserRole
from app.modules.consents.schemas import ConsentCreateRequest


def list_consents(db: Session, patient_id: uuid.UUID, user: User) -> list[Consent]:
    patient = clinical_access(db, patient_id, user, ClinicalAction.VIEW_CONSENTS)
    return (
        db.query(Consent)
        .filter(Consent.clinic_id == user.clinic_id, Consent.patient_id == patient.id)
        .order_by(Consent.created_at.desc(), Consent.id.desc())
        .all()
    )


def get_consent(db: Session, consent_id: uuid.UUID, user: User) -> Consent:
    consent = db.query(Consent).filter(Consent.id == consent_id, Consent.clinic_id == user.clinic_id).first()
    if consent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consentimento não encontrado.")
    clinical_access(db, consent.patient_id, user, ClinicalAction.VIEW_CONSENTS)
    return consent


def _own_patient(db: Session, patient_id: uuid.UUID, user: User) -> Patient:
    patient = db.get(Patient, patient_id)
    if patient is None or patient.clinic_id != user.clinic_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paciente não encontrado.")
    if user.role != UserRole.PATIENT or patient.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas o paciente pode gerir o próprio consentimento.",
        )
    return patient


def grant_consent(db: Session, patient_id: uuid.UUID, payload: ConsentCreateRequest, user: User) -> Consent:
    patient = _own_patient(db, patient_id, user)
    existing = (
        db.query(Consent)
        .filter(
            Consent.patient_id == patient.id,
            Consent.consent_type == payload.consent_type,
            Consent.purpose == payload.purpose,
            Consent.status == ConsentStatus.GRANTED,
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Consentimento já concedido.")

    consent = Consent(
        clinic_id=patient.clinic_id,
        patient_id=patient.id,
        consent_type=payload.consent_type,
        purpose=payload.purpose,
        policy_version=payload.policy_version,
        policy_text=payload.policy_text,
        status=ConsentStatus.GRANTED,
        granted_at=datetime.now(UTC),
        recorded_by_user_id=user.id,
    )
    db.add(consent)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Consentimento já concedido."
        ) from exc
    db.refresh(consent)
    return consent


def revoke_consent(db: Session, consent_id: uuid.UUID, user: User) -> Consent:
    consent = db.query(Consent).filter(Consent.id == consent_id, Consent.clinic_id == user.clinic_id).first()
    if consent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consentimento não encontrado.")
    _own_patient(db, consent.patient_id, user)
    if consent.status == ConsentStatus.REVOKED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Consentimento já revogado.")
    consent.status = ConsentStatus.REVOKED
    consent.revoked_at = datetime.now(UTC)
    db.commit()
    db.refresh(consent)
    return consent
