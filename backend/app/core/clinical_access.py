import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Patient, Staff, StaffRole, User, UserRole


def accessible_patient(db: Session, patient_id: uuid.UUID, user: User, *, write: bool = False) -> Patient:
    patient = db.query(Patient).filter(Patient.id == patient_id, Patient.clinic_id == user.clinic_id).first()
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paciente não encontrado.")
    if user.role == UserRole.PATIENT:
        if write or patient.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paciente não encontrado.")
        return patient
    if user.role != UserRole.STAFF:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissões clínicas.")
    staff = db.query(Staff).filter(Staff.user_id == user.id, Staff.clinic_id == user.clinic_id).first()
    if staff is None or staff.staff_role not in {StaffRole.DOCTOR, StaffRole.NURSE}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissões clínicas.")
    return patient


def clinical_staff(db: Session, user: User) -> Staff:
    if user.role != UserRole.STAFF:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissões clínicas.")
    staff = db.query(Staff).filter(Staff.user_id == user.id, Staff.clinic_id == user.clinic_id).first()
    if staff is None or staff.staff_role not in {StaffRole.DOCTOR, StaffRole.NURSE}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissões clínicas.")
    return staff
