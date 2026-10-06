"""
Helpers for the clinical workflow suites: every actor is a real logged-in
user driving the HTTP API (never a hand-built token or a mocked dependency).
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.core.config import settings
from app.models import AuditLog, Notification, User
from tests.account_support import PASSWORD

STAFF_ROLES = ("doctor", "nurse", "physiotherapist", "admin")
ALL_ROLES = (*STAFF_ROLES, "clinic_admin", "patient")


def identity(response) -> dict[str, str]:
    session = response.cookies.get(settings.COOKIE_NAME)
    csrf = response.cookies.get(settings.CSRF_COOKIE_NAME)
    assert session and csrf, response.text
    return {"session": session, "csrf": csrf}


def use(client: TestClient, who: dict[str, str]) -> dict[str, str]:
    """Switch the shared client to `who`; returns the CSRF header for unsafe methods."""
    client.cookies.clear()
    client.cookies.set(settings.COOKIE_NAME, who["session"])
    client.cookies.set(settings.CSRF_COOKIE_NAME, who["csrf"])
    return {settings.CSRF_HEADER_NAME: who["csrf"]}


def raw_headers(who: dict[str, str]) -> dict[str, str]:
    """Self-contained auth headers, for clients that must not share a cookie jar."""
    return {
        "Cookie": f"{settings.COOKIE_NAME}={who['session']}; {settings.CSRF_COOKIE_NAME}={who['csrf']}",
        settings.CSRF_HEADER_NAME: who["csrf"],
    }


@dataclass
class Tenant:
    clinic_id: str
    patient_id: str
    other_patient_id: str
    who: dict[str, dict[str, str]]
    staff_ids: dict[str, str]
    emails: dict[str, str]
    user_ids: dict[str, str] = field(default_factory=dict)

    def act(self, client: TestClient, role: str) -> dict[str, str]:
        return use(client, self.who[role])


def _login(client: TestClient, email: str) -> dict[str, str]:
    client.cookies.clear()
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return identity(response)


def make_tenant(client: TestClient, suffix: str) -> Tenant:
    """One clinic: clinic_admin, doctor, nurse, administrative staff, two patients."""
    response = client.post(
        "/api/v1/clinics",
        json={
            "clinic_name": f"Clinic {suffix}",
            "admin_full_name": f"Clinic Admin {suffix}",
            "admin_email": f"clinic_admin-{suffix}@example.pt",
            "admin_password": PASSWORD,
        },
    )
    assert response.status_code == 201, response.text
    clinic_id = response.json()["id"]
    who = {"clinic_admin": identity(response)}
    emails = {"clinic_admin": f"clinic_admin-{suffix}@example.pt"}
    staff_ids: dict[str, str] = {}

    for role in STAFF_ROLES:
        email = f"{role}-{suffix}@example.pt"
        created = client.post(
            "/api/v1/staff",
            headers=use(client, who["clinic_admin"]),
            json={
                "full_name": f"{role.title()} {suffix}",
                "email": email,
                "password": PASSWORD,
                "staff_role": role,
                "require_password_change": False,
            },
        )
        assert created.status_code == 201, created.text
        staff_ids[role] = created.json()["id"]
        emails[role] = email
        who[role] = _login(client, email)

    patient_ids = []
    for index, key in enumerate(("patient", "other_patient")):
        email = f"{key.replace('_', '-')}-{suffix}@example.pt"
        client.cookies.clear()
        registered = client.post(
            "/api/v1/patients/register",
            json={
                "clinic_id": clinic_id,
                "full_name": f"Patient {index} {suffix}",
                "email": email,
                "password": PASSWORD,
            },
        )
        assert registered.status_code == 201, registered.text
        patient_ids.append(registered.json()["id"])
        who[key] = identity(registered)
        emails[key] = email

    tenant = Tenant(
        clinic_id=clinic_id,
        patient_id=patient_ids[0],
        other_patient_id=patient_ids[1],
        who=who,
        staff_ids=staff_ids,
        emails=emails,
    )
    with client.session_factory() as db:  # type: ignore[attr-defined]
        for key, email in emails.items():
            tenant.user_ids[key] = str(db.query(User).filter(User.email_matches(email)).one().id)
    # Explicit care-team membership is required for professional access.
    for role in ("doctor", "nurse", "physiotherapist"):
        response = client.post(
            f"/api/v1/patients/{tenant.patient_id}/care-team",
            headers=tenant.act(client, "clinic_admin"),
            json={"staff_id": tenant.staff_ids[role]},
        )
        assert response.status_code == 201, response.text
    return tenant


def slot(days: int = 3, minutes: int = 0) -> str:
    base = datetime.now(UTC).replace(hour=9, minute=0, second=0, microsecond=0)
    return (base + timedelta(days=days, minutes=minutes)).isoformat()


def book(client: TestClient, tenant: Tenant, *, role: str = "doctor", **overrides) -> dict:
    payload = {
        "patient_id": tenant.patient_id,
        "staff_id": tenant.staff_ids["doctor"],
        "scheduled_at": slot(),
        "duration_minutes": 30,
        **overrides,
    }
    response = client.post("/api/v1/appointments", headers=tenant.act(client, role), json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def write_record(client: TestClient, tenant: Tenant, content: str = "Clinical note") -> dict:
    response = client.post(
        f"/api/v1/patients/{tenant.patient_id}/medical-records",
        headers=tenant.act(client, "doctor"),
        json={"title": "Assessment", "content": content},
    )
    assert response.status_code == 201, response.text
    return response.json()


def prescribe(client: TestClient, tenant: Tenant, name: str = "Drug A") -> dict:
    response = client.post(
        f"/api/v1/patients/{tenant.patient_id}/medications",
        headers=tenant.act(client, "doctor"),
        json={"name": name, "dosage": "10 mg", "start_date": "2026-01-01"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def grant(client: TestClient, tenant: Tenant, purpose: str = "Direct care") -> dict:
    response = client.post(
        f"/api/v1/patients/{tenant.patient_id}/consents",
        headers=tenant.act(client, "patient"),
        json={"consent_type": "treatment", "purpose": purpose},
    )
    assert response.status_code == 201, response.text
    return response.json()


def notify(client: TestClient, tenant: Tenant, role: str, title: str = "Aviso") -> str:
    """Notifications have no automatic producer yet, so tests seed them directly."""
    with client.session_factory() as db:  # type: ignore[attr-defined]
        row = Notification(
            clinic_id=tenant.clinic_id,
            user_id=uuid.UUID(tenant.user_ids[role]),
            title=title,
            message="Mensagem",
        )
        db.add(row)
        db.commit()
        return str(row.id)


def audit(client: TestClient, action: str, *, resource_id: str | None = None) -> list[AuditLog]:
    with client.session_factory() as db:  # type: ignore[attr-defined]
        rows = [row for row in db.query(AuditLog).order_by(AuditLog.timestamp).all() if row.action.value == action]
        if resource_id is not None:
            rows = [row for row in rows if str(row.resource_id) == resource_id]
        for row in rows:
            db.expunge(row)
        return rows
