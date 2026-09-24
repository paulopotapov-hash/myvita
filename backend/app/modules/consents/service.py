import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Consent, ConsentStatus, Patient, User, UserRole
from app.modules.consents.schemas import ConsentCreateRequest


def _patient_for_user(db: Session, user: User) -> Patient | None:
    return db.query(Patient).filter(Patient.user_id == user.id).first()


def get_accessible_patient(db: Session, patient_id: uuid.UUID, user: User) -> Patient:
    patient = db.get(Patient, patient_id)
    if patient is None or patient.clinic_id != user.clinic_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paciente não encontrado.")
    if user.role == UserRole.PATIENT:
        own_patient = _patient_for_user(db, user)
        if own_patient is None or own_patient.id != patient.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paciente não encontrado.")
    return patient


def list_consents(db: Session, patient_id: uuid.UUID, user: User) -> list[Consent]:
    patient = get_accessible_patient(db, patient_id, user)
    return (
        db.query(Consent)
        .filter(Consent.clinic_id == user.clinic_id, Consent.patient_id == patient.id)
        .order_by(Consent.created_at.desc(), Consent.id.desc())
        .all()
    )


def get_consent(db: Session, consent_id: uuid.UUID, user: User) -> Consent:
    consent = (
        db.query(Consent)
        .filter(Consent.id == consent_id, Consent.clinic_id == user.clinic_id)
        .first()
    )
    if consent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consentimento não encontrado.")
    if user.role == UserRole.PATIENT:
        own_patient = _patient_for_user(db, user)
        if own_patient is None or consent.patient_id != own_patient.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Consentimento não encontrado."
            )
    return consent


def grant_consent(
    db: Session, patient_id: uuid.UUID, payload: ConsentCreateRequest, user: User
) -> Consent:
    patient = get_accessible_patient(db, patient_id, user)
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
    consent = get_consent(db, consent_id, user)
    if consent.status == ConsentStatus.REVOKED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Consentimento já revogado.")
    consent.status = ConsentStatus.REVOKED
    consent.revoked_at = datetime.now(UTC)
    db.commit()
    db.refresh(consent)
    return consent
