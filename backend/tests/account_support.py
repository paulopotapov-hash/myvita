"""
Shared helpers for the account-lifecycle / MFA / password-reset suites.

Everything goes through the real HTTP app against the migrated test
database (tests/conftest.py truncates it before every test).
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core import mfa
from app.core.database import get_db
from app.main import app
from tests.conftest import TEST_DATABASE_URL, csrf_headers

PASSWORD = "SenhaForte123!"
NEW_PASSWORD = "OutraSenhaForte456!"


@contextmanager
def http_client() -> Iterator[TestClient]:
    engine = create_engine(TEST_DATABASE_URL, future=True)
    session_factory = sessionmaker(bind=engine, future=True)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            client.session_factory = session_factory  # type: ignore[attr-defined]
            yield client
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


class TotpClock:
    """Deterministic TOTP time steps, so replay protection is testable."""

    def __init__(self, start: int = 10_000_000) -> None:
        self.step = start

    def advance(self, steps: int = 1) -> None:
        self.step += steps

    def code(self, secret: str, offset: int = 0) -> str:
        return mfa.hotp(secret, self.step + offset)


def post(client: TestClient, path: str, json: dict | None = None):
    return client.post(path, json=json, headers=csrf_headers(client))


def onboard_clinic(client: TestClient, email: str = "admin@clinica.pt", name: str = "Clínica Teste") -> dict:
    response = client.post(
        "/api/v1/clinics",
        json={"clinic_name": name, "admin_full_name": "Admin Teste", "admin_email": email, "admin_password": PASSWORD},
    )
    assert response.status_code == 201, response.text
    return response.json()


def login(client: TestClient, email: str, password: str = PASSWORD):
    client.cookies.clear()
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def create_staff(
    client: TestClient, email: str, *, require_password_change: bool = False, staff_role: str = "doctor"
) -> dict:
    """Created by the clinic admin currently logged in on `client`."""
    response = post(
        client,
        "/api/v1/staff",
        {
            "full_name": "Profissional Teste",
            "email": email,
            "password": PASSWORD,
            "staff_role": staff_role,
            "require_password_change": require_password_change,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def register_patient(client: TestClient, clinic_id: str, email: str) -> dict:
    client.cookies.clear()
    response = client.post(
        "/api/v1/patients/register",
        json={"clinic_id": clinic_id, "full_name": "Paciente Teste", "email": email, "password": PASSWORD},
    )
    assert response.status_code == 201, response.text
    return response.json()


@dataclass
class Enrolment:
    secret: str
    recovery_codes: list[str]


def enrol_mfa(client: TestClient, clock: TotpClock) -> Enrolment:
    """Enrol MFA for the user logged in on `client` (session becomes MFA-verified)."""
    setup = post(client, "/api/v1/auth/mfa/setup")
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    enabled = post(client, "/api/v1/auth/mfa/enable", {"code": clock.code(secret)})
    assert enabled.status_code == 200, enabled.text
    clock.advance()
    return Enrolment(secret=secret, recovery_codes=enabled.json()["recovery_codes"])


def user_id_by_email(client: TestClient, email: str) -> str:
    from app.models import User

    with client.session_factory() as db:  # type: ignore[attr-defined]
        user = db.query(User).filter(User.email_matches(email)).one()
        return str(user.id)


def audit_rows(client: TestClient, action: str) -> list:
    from app.models import AuditLog

    with client.session_factory() as db:  # type: ignore[attr-defined]
        return [row for row in db.query(AuditLog).all() if row.action.value == action]
