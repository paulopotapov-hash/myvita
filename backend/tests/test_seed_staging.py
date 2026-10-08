"""The synthetic staging seed is an operator tool: it must create its patients
regardless of the public self-registration allowlist (production default: empty)."""
from scripts.seed_staging import seed

from app.core.config import settings
from app.models import Patient, User, UserRole


def test_seed_creates_patients_without_public_registration_allowlist(db_session, monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_CLINIC_IDS", [])
    monkeypatch.setattr(settings, "ALLOW_PUBLIC_PATIENT_REGISTRATION", False)

    created = seed(db_session, "SenhaForte123!", "seed.example")

    assert {"patient-a@seed.example", "patient-b@seed.example"} <= set(created)
    for email in ("patient-a@seed.example", "patient-b@seed.example"):
        user = db_session.query(User).filter(User.email == email).one()
        assert user.role == UserRole.PATIENT
        patient = db_session.query(Patient).filter(Patient.user_id == user.id).one()
        assert patient.clinic_id == user.clinic_id
    # Idempotent: a second run creates nothing.
    assert seed(db_session, "SenhaForte123!", "seed.example") == []
