"""
Audit logging tests.

Deliberately does NOT use the `db_session` fixture (savepoint + rollback):
record_audit_event() writes through its own independent session (see
app/core/audit.py's docstring for why), so it bypasses that fixture's
rollback entirely. These tests use the same create_all/drop_all HTTP-client
pattern as test_auth_hardening.py instead, and read the audit_logs table
back through app.core.database.SessionLocal — the same session factory the
app itself writes through.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, SessionLocal, get_db
from app.core.rate_limit import limiter
from app.main import app
from app.models import AuditAction, AuditLog, AuditResult
from tests.conftest import TEST_DATABASE_URL, csrf_headers


@pytest.fixture()
def client():
    engine = create_engine(TEST_DATABASE_URL, future=True)
    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(bind=engine, future=True)

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    limiter.reset()
    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def _audit_events(action: AuditAction) -> list[AuditLog]:
    db = SessionLocal()
    try:
        return db.query(AuditLog).filter(AuditLog.action == action).order_by(AuditLog.timestamp).all()
    finally:
        db.close()


def _onboard_clinic(client, email="admin@clinica.pt", password="SenhaForte123!"):
    return client.post(
        "/api/v1/clinics",
        json={
            "clinic_name": "Clínica Teste",
            "nif": "500999999",
            "admin_full_name": "Admin Teste",
            "admin_email": email,
            "admin_password": password,
        },
    )


def test_clinic_created_logs_audit_event_with_correct_actor_and_clinic(client):
    r = _onboard_clinic(client)
    clinic_id = r.json()["id"]

    events = _audit_events(AuditAction.CLINIC_CREATED)
    assert len(events) == 1
    assert str(events[0].clinic_id) == clinic_id
    assert events[0].actor_email == "admin@clinica.pt"
    assert events[0].result == AuditResult.SUCCESS
    assert events[0].timestamp is not None


def test_login_success_and_failure_both_logged(client):
    _onboard_clinic(client)

    client.post("/api/v1/auth/login", json={"email": "admin@clinica.pt", "password": "SenhaForte123!"})
    client.post("/api/v1/auth/login", json={"email": "admin@clinica.pt", "password": "errada"})
    client.post("/api/v1/auth/login", json={"email": "ninguem@example.com", "password": "qualquer123"})

    successes = _audit_events(AuditAction.LOGIN_SUCCESS)
    failures = _audit_events(AuditAction.LOGIN_FAILURE)

    assert len(successes) == 1
    assert successes[0].actor_email == "admin@clinica.pt"

    assert len(failures) == 2
    # Failed attempt against a real account still resolves clinic/actor...
    assert any(f.actor_email == "admin@clinica.pt" and f.clinic_id is not None for f in failures)
    # ...while an unknown email has no user/clinic to attach, but is still logged.
    assert any(f.actor_email == "ninguem@example.com" and f.actor_user_id is None for f in failures)


def test_patient_and_staff_creation_logged_with_correct_clinic(client):
    clinic_id = _onboard_clinic(client).json()["id"]

    client.post(
        "/api/v1/patients/register",
        json={
            "clinic_id": clinic_id,
            "full_name": "Paciente Teste",
            "email": "paciente@example.com",
            "password": "SenhaForte123!",
        },
    )
    client.post("/api/v1/auth/login", json={"email": "admin@clinica.pt", "password": "SenhaForte123!"})
    client.post(
        "/api/v1/staff",
        json={
            "full_name": "Enfermeiro Teste",
            "email": "enfermeiro@clinica.pt",
            "password": "SenhaForte123!",
            "staff_role": "nurse",
        },
        headers=csrf_headers(client),
    )

    patient_events = _audit_events(AuditAction.PATIENT_CREATED)
    staff_events = _audit_events(AuditAction.STAFF_CREATED)

    assert len(patient_events) == 1
    assert str(patient_events[0].clinic_id) == clinic_id

    assert len(staff_events) == 1
    assert str(staff_events[0].clinic_id) == clinic_id
    assert staff_events[0].actor_email == "admin@clinica.pt"


def test_permission_denied_logged_for_cross_role_access(client):
    """A patient trying to hit a staff-only endpoint must be DENIED and logged."""
    clinic_id = _onboard_clinic(client).json()["id"]
    client.post(
        "/api/v1/patients/register",
        json={
            "clinic_id": clinic_id,
            "full_name": "Paciente Teste",
            "email": "paciente@example.com",
            "password": "SenhaForte123!",
        },
    )
    # patient session is already active from register() auto-login
    r = client.post(
        "/api/v1/staff",
        json={
            "full_name": "X",
            "email": "x@clinica.pt",
            "password": "SenhaForte123!",
            "staff_role": "nurse",
        },
        headers=csrf_headers(client),
    )
    assert r.status_code == 403

    events = _audit_events(AuditAction.PERMISSION_DENIED)
    assert len(events) == 1
    assert events[0].actor_email == "paciente@example.com"
    assert events[0].result == AuditResult.DENIED


def test_csrf_failure_logged(client):
    _onboard_clinic(client)
    client.post("/api/v1/auth/login", json={"email": "admin@clinica.pt", "password": "SenhaForte123!"})

    # Deliberately omit the CSRF header.
    r = client.post(
        "/api/v1/staff",
        json={
            "full_name": "X",
            "email": "x@clinica.pt",
            "password": "SenhaForte123!",
            "staff_role": "nurse",
        },
    )
    assert r.status_code == 403

    events = _audit_events(AuditAction.CSRF_FAILURE)
    assert len(events) == 1
    assert events[0].actor_email == "admin@clinica.pt"


def test_clinical_access_logged_separately_for_patient_and_staff(client):
    clinic_id = _onboard_clinic(client).json()["id"]
    client.post(
        "/api/v1/patients/register",
        json={
            "clinic_id": clinic_id,
            "full_name": "Paciente Teste",
            "email": "paciente@example.com",
            "password": "SenhaForte123!",
        },
    )
    client.get("/api/v1/appointments")  # patient viewing their own list

    client.post("/api/v1/auth/login", json={"email": "admin@clinica.pt", "password": "SenhaForte123!"})
    client.get("/api/v1/appointments")  # staff/admin viewing the clinic's list

    patient_views = _audit_events(AuditAction.PATIENT_VIEWED_OWN_RECORD)
    staff_views = _audit_events(AuditAction.STAFF_VIEWED_APPOINTMENT)

    assert len(patient_views) == 1
    assert patient_views[0].actor_email == "paciente@example.com"
    assert len(staff_views) == 1
    assert staff_views[0].actor_email == "admin@clinica.pt"


def test_no_secrets_ever_appear_in_audit_log(client):
    """
    Registers/logs in with a distinctive password and asserts it never shows
    up anywhere in the audit_logs table — metadata included.
    """
    secret_password = "SenhaMuitoSecreta987!"  # noqa: S105 (test fixture value, not a real credential)
    _onboard_clinic(client, password=secret_password)
    client.post("/api/v1/auth/login", json={"email": "admin@clinica.pt", "password": secret_password})

    db = SessionLocal()
    try:
        rows = db.query(AuditLog).all()
    finally:
        db.close()

    for row in rows:
        assert secret_password not in (row.actor_email or "")
        assert secret_password not in str(row.event_metadata or {})
        # No column on this model can ever hold a raw JWT/cookie/CSRF token —
        # this just double-checks nothing was ever bolted onto metadata.
        for forbidden in ("password", "jwt", "cookie", "csrf_token"):
            if row.event_metadata:
                assert forbidden not in str(row.event_metadata).lower()
