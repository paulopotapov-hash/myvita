from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.security import create_access_token, generate_csrf_token, hash_password
from app.main import app
from app.models import Clinic, Invitation, Patient, Staff, StaffRole, User, UserRole

PASSWORD = "SenhaForte123!"


@pytest.fixture()
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app, base_url="http://testserver") as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _clinic_user(
    db,
    *,
    name: str,
    email: str,
    role: UserRole,
    staff_role: StaffRole | None = None,
    clinic: Clinic | None = None,
):
    clinic = clinic or Clinic(name=name)
    if clinic.id is None:
        db.add(clinic)
        db.flush()
    user = User(
        email=email,
        full_name=email,
        hashed_password=hash_password(PASSWORD),
        role=role,
        clinic_id=clinic.id,
    )
    db.add(user)
    db.flush()
    if role == UserRole.STAFF:
        db.add(Staff(user_id=user.id, clinic_id=clinic.id, staff_role=staff_role or StaffRole.DOCTOR))
    if role == UserRole.PATIENT:
        db.add(Patient(user_id=user.id, clinic_id=clinic.id))
    db.commit()
    return clinic, user


def _authenticate(client: TestClient, user: User) -> dict[str, str]:
    from app.core.config import settings

    client.cookies.set(settings.COOKIE_NAME, create_access_token(user))
    csrf = generate_csrf_token(user)
    client.cookies.set(settings.CSRF_COOKIE_NAME, csrf)
    return {settings.CSRF_HEADER_NAME: csrf}


def _invite_staff(client, headers, email="doctor@example.com"):
    return client.post(
        "/api/v1/invitations/staff",
        headers=headers,
        json={"email": email, "full_name": "Doctor Invited", "staff_role": "doctor"},
    )


def test_valid_invitation_is_hashed_single_use_and_tenant_bound(client, db_session):
    clinic, admin = _clinic_user(
        db_session, name="Clinic A", email="admin-a@example.com", role=UserRole.CLINIC_ADMIN
    )
    headers = _authenticate(client, admin)
    created = _invite_staff(client, headers)
    assert created.status_code == 201
    token = created.json()["token"]
    stored = db_session.query(Invitation).filter(Invitation.id == created.json()["id"]).one()
    assert stored.token_hash != token
    assert token not in stored.token_hash

    accepted = client.post(
        "/api/v1/invitations/accept", json={"token": token, "password": "NovaSenhaForte123!"}
    )
    assert accepted.status_code == 200
    assert accepted.json()["clinic_id"] == str(clinic.id)
    assert accepted.json()["role"] == "staff"
    user = db_session.query(User).filter(User.email == "doctor@example.com").one()
    assert user.clinic_id == clinic.id
    assert user.staff_profile.staff_role == StaffRole.DOCTOR

    reused = client.post(
        "/api/v1/invitations/accept", json={"token": token, "password": "OutraSenhaForte123!"}
    )
    assert reused.status_code == 410


def test_expired_and_unknown_invitations_are_rejected(client, db_session):
    _, admin = _clinic_user(
        db_session, name="Clinic A", email="admin-exp@example.com", role=UserRole.CLINIC_ADMIN
    )
    created = _invite_staff(client, _authenticate(client, admin), "expired@example.com")
    token = created.json()["token"]
    invitation = db_session.query(Invitation).filter(Invitation.id == created.json()["id"]).one()
    invitation.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()

    expired = client.post("/api/v1/invitations/accept", json={"token": token, "password": PASSWORD})
    unknown = client.post(
        "/api/v1/invitations/accept",
        json={"token": "not-a-real-invitation-token-value-000000000000", "password": PASSWORD},
    )
    assert expired.status_code == 410
    assert unknown.status_code == 404


def test_invitation_token_never_uses_query_string_and_tampering_is_rejected(client, db_session):
    _, admin = _clinic_user(
        db_session, name="Clinic Preview", email="admin-preview@example.com", role=UserRole.CLINIC_ADMIN
    )
    created = _invite_staff(client, _authenticate(client, admin), "preview@example.com")
    token = created.json()["token"]

    preview = client.post("/api/v1/invitations/preview", json={"token": token})
    assert preview.status_code == 200
    assert preview.json()["email"] == "preview@example.com"
    assert client.get(f"/api/v1/invitations/preview?token={token}").status_code == 405
    tampered = f"{token[:-1]}{'A' if token[-1] != 'A' else 'B'}"
    assert client.post("/api/v1/invitations/preview", json={"token": tampered}).status_code == 404


def test_cross_tenant_and_privilege_escalation_inputs_are_blocked(client, db_session):
    clinic_a, admin_a = _clinic_user(
        db_session, name="Clinic A", email="admin-a2@example.com", role=UserRole.CLINIC_ADMIN
    )
    clinic_b, patient_b = _clinic_user(
        db_session, name="Clinic B", email="patient-b@example.com", role=UserRole.PATIENT
    )
    malicious = client.post(
        "/api/v1/invitations/staff",
        headers=_authenticate(client, admin_a),
        json={
            "email": "cross@example.com",
            "full_name": "Cross Tenant",
            "staff_role": "doctor",
            "clinic_id": str(clinic_b.id),
            "role": "clinic_admin",
        },
    )
    assert malicious.status_code == 422

    forbidden = client.post(
        "/api/v1/invitations/staff",
        headers=_authenticate(client, patient_b),
        json={"email": "escalate@example.com", "full_name": "Escalate", "staff_role": "doctor"},
    )
    assert forbidden.status_code == 403
    assert db_session.query(Invitation).filter(Invitation.clinic_id == clinic_a.id).count() == 0


def test_patient_invitation_requires_authorized_clinical_actor_and_strong_password(client, db_session):
    clinic, doctor = _clinic_user(
        db_session,
        name="Clinic Clinical",
        email="doctor-inviter@example.com",
        role=UserRole.STAFF,
        staff_role=StaffRole.DOCTOR,
    )
    created = client.post(
        "/api/v1/invitations/patients",
        headers=_authenticate(client, doctor),
        json={"email": "new-patient@example.com", "full_name": "New Patient"},
    )
    assert created.status_code == 201
    weak = client.post(
        "/api/v1/invitations/accept", json={"token": created.json()["token"], "password": "password"}
    )
    assert weak.status_code == 422
    assert db_session.query(User).filter(User.email == "new-patient@example.com").first() is None
    assert created.json()["clinic_id"] == str(clinic.id)


def test_password_change_requires_current_password_and_revokes_old_session(client, db_session):
    _, admin = _clinic_user(
        db_session, name="Password Clinic", email="password-admin@example.com", role=UserRole.CLINIC_ADMIN
    )
    headers = _authenticate(client, admin)
    from app.core.config import settings

    stolen_cookie = client.cookies.get(settings.COOKIE_NAME)
    wrong = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": "WrongPassword123!", "new_password": "NovaSenhaForte123!"},
    )
    assert wrong.status_code == 400

    changed = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": PASSWORD, "new_password": "NovaSenhaForte123!"},
    )
    assert changed.status_code == 204

    with TestClient(app, base_url="http://testserver") as attacker:
        attacker.cookies.set(settings.COOKIE_NAME, stolen_cookie)
        assert attacker.get("/api/v1/auth/me").status_code == 401

    client.cookies.clear()
    old_login = client.post(
        "/api/v1/auth/login", json={"email": admin.email, "password": PASSWORD}
    )
    new_login = client.post(
        "/api/v1/auth/login", json={"email": admin.email, "password": "NovaSenhaForte123!"}
    )
    assert old_login.status_code == 401
    assert new_login.status_code == 200


def test_admin_deactivation_revokes_staff_session_and_is_tenant_scoped(client, db_session):
    clinic, admin = _clinic_user(
        db_session, name="Offboarding Clinic", email="offboard-admin@example.com", role=UserRole.CLINIC_ADMIN
    )
    _, doctor = _clinic_user(
        db_session,
        name="Offboarding Clinic",
        email="offboard-doctor@example.com",
        role=UserRole.STAFF,
        staff_role=StaffRole.DOCTOR,
        clinic=clinic,
    )
    other_clinic, other_admin = _clinic_user(
        db_session, name="Other Clinic", email="other-admin@example.com", role=UserRole.CLINIC_ADMIN
    )
    staff = doctor.staff_profile
    doctor_token = create_access_token(doctor)

    forbidden = client.post(
        f"/api/v1/staff/{staff.id}/deactivate",
        headers=_authenticate(client, other_admin),
    )
    assert forbidden.status_code == 404
    assert doctor.is_active is True
    assert other_clinic.id != clinic.id

    deactivated = client.post(
        f"/api/v1/staff/{staff.id}/deactivate",
        headers=_authenticate(client, admin),
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False

    client.cookies.clear()
    from app.core.config import settings

    client.cookies.set(settings.COOKIE_NAME, doctor_token)
    assert client.get("/api/v1/auth/me").status_code == 401


def test_direct_staff_password_creation_is_disabled_outside_test_escape_hatch(
    client, db_session, monkeypatch
):
    _, admin = _clinic_user(
        db_session, name="Invite Only Clinic", email="invite-only@example.com", role=UserRole.CLINIC_ADMIN
    )
    from app.core.config import settings

    monkeypatch.setattr(settings, "ALLOW_DIRECT_STAFF_CREATION", False)
    response = client.post(
        "/api/v1/staff",
        headers=_authenticate(client, admin),
        json={
            "email": "legacy-password@example.com",
            "full_name": "Legacy Account",
            "password": PASSWORD,
            "staff_role": "doctor",
        },
    )
    assert response.status_code == 403
    assert db_session.query(User).filter(User.email == "legacy-password@example.com").first() is None


def test_admin_can_deactivate_patient_but_not_cross_tenant(client, db_session):
    clinic, admin = _clinic_user(
        db_session, name="Patient Offboarding", email="patient-admin@example.com", role=UserRole.CLINIC_ADMIN
    )
    _, patient_user = _clinic_user(
        db_session,
        name="Patient Offboarding",
        email="offboard-patient@example.com",
        role=UserRole.PATIENT,
        clinic=clinic,
    )
    _, other_admin = _clinic_user(
        db_session, name="Other Patient Clinic", email="other-patient-admin@example.com", role=UserRole.CLINIC_ADMIN
    )
    patient = patient_user.patient_profile
    old_token = create_access_token(patient_user)

    assert client.post(
        f"/api/v1/patients/{patient.id}/deactivate",
        headers=_authenticate(client, other_admin),
    ).status_code == 404
    response = client.post(
        f"/api/v1/patients/{patient.id}/deactivate",
        headers=_authenticate(client, admin),
    )
    assert response.status_code == 200
    assert response.json()["is_active"] is False
    assert set(response.json()) == {"id", "clinic_id", "full_name", "is_active"}

    from app.core.config import settings

    client.cookies.clear()
    client.cookies.set(settings.COOKIE_NAME, old_token)
    assert client.get("/api/v1/auth/me").status_code == 401
