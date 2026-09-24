"""
These tests exist because a manual smoke test during development caught a
real bug: ORM-level cascade="all, delete-orphan" on Clinic's relationships
silently overrode the DB's ON DELETE RESTRICT, letting a clinic with
patients be deleted. Keep these tests so that bug (and its class) can't
come back unnoticed.
"""
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.security import hash_password
from app.models import Appointment, Clinic, Patient, Staff, StaffRole, User, UserRole


def _make_clinic_with_full_graph(db):
    clinic = Clinic(name="Test Clinic", nif="000111222")
    db.add(clinic)
    db.flush()

    doctor_user = User(
        email="doctor@test.pt", full_name="Dr. Test", hashed_password=hash_password("x"), role=UserRole.STAFF, clinic_id=clinic.id
    )
    db.add(doctor_user)
    db.flush()
    staff = Staff(user_id=doctor_user.id, clinic_id=clinic.id, staff_role=StaffRole.DOCTOR)
    db.add(staff)

    patient_user = User(
        email="patient@test.pt", full_name="Patient Test", hashed_password=hash_password("y"), role=UserRole.PATIENT, clinic_id=clinic.id
    )
    db.add(patient_user)
    db.flush()
    patient = Patient(user_id=patient_user.id, clinic_id=clinic.id, birth_date=date(1990, 1, 1))
    db.add(patient)
    db.flush()

    appt = Appointment(clinic_id=clinic.id, patient_id=patient.id, staff_id=staff.id, scheduled_at=datetime.now(UTC))
    db.add(appt)
    db.commit()
    return clinic, staff, patient, appt


def test_clinic_with_dependents_cannot_be_deleted(db_session):
    clinic, _, _, _ = _make_clinic_with_full_graph(db_session)

    db_session.delete(clinic)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_staff_with_appointment_history_cannot_be_deleted(db_session):
    _, staff, _, _ = _make_clinic_with_full_graph(db_session)

    db_session.delete(staff)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_patient_with_appointment_history_cannot_be_deleted(db_session):
    _, _, patient, _ = _make_clinic_with_full_graph(db_session)
    db_session.delete(patient)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_duplicate_email_rejected(db_session):
    clinic = Clinic(name="C", nif="1")
    db_session.add(clinic)
    db_session.flush()
    db_session.add(User(email="dup@test.pt", full_name="Dup One", hashed_password=hash_password("a"), role=UserRole.PATIENT, clinic_id=clinic.id))
    db_session.commit()

    db_session.add(User(email="dup@test.pt", full_name="Dup Two", hashed_password=hash_password("b"), role=UserRole.PATIENT, clinic_id=clinic.id))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_one_patient_profile_per_user(db_session):
    clinic = Clinic(name="C2", nif="2")
    db_session.add(clinic)
    db_session.flush()
    user = User(email="onepatient@test.pt", full_name="One Patient", hashed_password=hash_password("a"), role=UserRole.PATIENT, clinic_id=clinic.id)
    db_session.add(user)
    db_session.flush()
    db_session.add(Patient(user_id=user.id, clinic_id=clinic.id))
    db_session.commit()

    db_session.add(Patient(user_id=user.id, clinic_id=clinic.id))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
