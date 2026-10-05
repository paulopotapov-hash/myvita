"""
Synthetic, repeatable two-clinic dataset for the Phase 1 validation suites.

    Clinic A: clinic admin, doctor, nurse, administrative staff, patients A1 + A2
    Clinic B: clinic admin, doctor, nurse, administrative staff, patient B1

Every identity is created through the public API (onboarding, staff creation,
patient registration), so the dataset also exercises the real creation paths.
Each patient additionally gets one appointment, medical record, medication and
consent, which makes cross-tenant / cross-patient leaks easy to prove: any
response that contains a foreign identifier is a failure.

All credentials below are synthetic and exist only inside the throwaway test
database.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.database import Base, get_db
from app.core.rate_limit import limiter
from app.main import app
from tests.conftest import TEST_DATABASE_URL

PASSWORD = "Phase1-Synthetic-Pass-9!"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
RECORD_MARKER = "PHASE1-CLINICAL-CONTENT-MARKER"
START = "2031-03-10T09:00:00+00:00"


class Actor:
    """One identity with its own cookie jar; adds the CSRF header automatically."""

    def __init__(self, key: str, email: str = "", *, raise_server_exceptions: bool = True):
        self.key = key
        self.email = email
        self.client = TestClient(app, raise_server_exceptions=raise_server_exceptions)
        self.user_id: str | None = None
        self.clinic_id: str | None = None
        self.patient_id: str | None = None
        self.staff_id: str | None = None
        self.res: dict[str, str] = {}

    def call(
        self,
        method: str,
        path: str,
        json: Any = None,
        *,
        csrf: bool | str = True,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ):
        sent = dict(headers or {})
        if isinstance(csrf, str):
            sent[settings.CSRF_HEADER_NAME] = csrf
        elif csrf and method.upper() not in SAFE_METHODS:
            token = self.client.cookies.get(settings.CSRF_COOKIE_NAME)
            if token:
                sent[settings.CSRF_HEADER_NAME] = token
        return self.client.request(method.upper(), path, json=json, headers=sent, **kwargs)

    def get(self, path: str, **kwargs: Any):
        return self.call("GET", path, **kwargs)

    def post(self, path: str, json: Any = None, **kwargs: Any):
        return self.call("POST", path, json, **kwargs)

    def patch(self, path: str, json: Any = None, **kwargs: Any):
        return self.call("PATCH", path, json, **kwargs)

    @property
    def csrf_token(self) -> str | None:
        return self.client.cookies.get(settings.CSRF_COOKIE_NAME)

    @property
    def session_token(self) -> str | None:
        return self.client.cookies.get(settings.COOKIE_NAME)

    def login(self, password: str = PASSWORD):
        limiter.reset()
        response = self.client.post("/api/v1/auth/login", json={"email": self.email, "password": password})
        if response.status_code == 200:
            self.load_identity()
        return response

    def load_identity(self) -> dict[str, Any]:
        me = self.get("/api/v1/auth/me")
        assert me.status_code == 200, me.text
        body = me.json()
        self.user_id = body["id"]
        self.clinic_id = body["clinic_id"]
        self.patient_id = body.get("patient_id")
        return body


@dataclass
class Tenant:
    name: str
    clinic_id: str
    admin: Actor
    doctor: Actor
    nurse: Actor
    staff_admin: Actor
    patients: dict[str, Actor] = field(default_factory=dict)

    @property
    def staff(self) -> list[Actor]:
        return [self.doctor, self.nurse, self.staff_admin]

    @property
    def everyone(self) -> list[Actor]:
        return [self.admin, *self.staff, *self.patients.values()]


@dataclass
class World:
    a: Tenant
    b: Tenant
    session_factory: sessionmaker[Session]

    def db(self) -> Session:
        return self.session_factory()


def _new_tenant(name: str, patient_keys: list[str]) -> Tenant:
    limiter.reset()
    admin = Actor(f"{name}-clinic-admin", f"clinic-admin-{name}@phase1.example")
    created = admin.post(
        "/api/v1/clinics",
        json={
            "clinic_name": f"Phase1 Clinic {name.upper()}",
            "admin_full_name": f"Clinic Admin {name.upper()}",
            "admin_email": admin.email,
            "admin_password": PASSWORD,
        },
        csrf=False,
    )
    assert created.status_code == 201, created.text
    admin.load_identity()
    clinic_id = created.json()["id"]

    staff: dict[str, Actor] = {}
    for staff_role in ("doctor", "nurse", "admin"):
        actor = Actor(f"{name}-{staff_role}", f"{staff_role}-{name}@phase1.example")
        response = admin.post(
            "/api/v1/staff",
            json={
                "full_name": f"{staff_role.title()} {name.upper()}",
                "email": actor.email,
                "password": PASSWORD,
                "staff_role": staff_role,
            },
        )
        assert response.status_code == 201, response.text
        actor.staff_id = response.json()["id"]
        assert actor.login().status_code == 200
        staff[staff_role] = actor

    tenant = Tenant(name, clinic_id, admin, staff["doctor"], staff["nurse"], staff["admin"])
    for key in patient_keys:
        limiter.reset()
        patient = Actor(f"{name}-{key}", f"patient-{key}@phase1.example")
        response = patient.post(
            "/api/v1/patients/register",
            json={
                "clinic_id": clinic_id,
                "full_name": f"Patient {key.upper()}",
                "email": patient.email,
                "password": PASSWORD,
                "birth_date": "1990-01-02",
                "phone": "910000000",
            },
            csrf=False,
        )
        assert response.status_code == 201, response.text
        patient.load_identity()
        tenant.patients[key] = patient
    return tenant


def _seed_clinical_resources(tenant: Tenant, hour_offset: int) -> None:
    doctor = tenant.doctor
    for index, (key, patient) in enumerate(tenant.patients.items()):
        hour = 9 + hour_offset + index
        appointment = doctor.post(
            "/api/v1/appointments",
            json={
                "patient_id": patient.patient_id,
                "staff_id": doctor.staff_id,
                "scheduled_at": f"2031-03-10T{hour:02d}:00:00+00:00",
                "duration_minutes": 30,
                "reason": f"seed-reason-{tenant.name}-{key}",
            },
        )
        assert appointment.status_code == 201, appointment.text
        record = doctor.post(
            f"/api/v1/patients/{patient.patient_id}/medical-records",
            json={"title": f"Seed record {tenant.name}-{key}", "content": f"{RECORD_MARKER} {tenant.name}-{key}"},
        )
        assert record.status_code == 201, record.text
        medication = doctor.post(
            f"/api/v1/patients/{patient.patient_id}/medications",
            json={"name": "Seedamol", "dosage": "10 mg", "start_date": "2031-03-01"},
        )
        assert medication.status_code == 201, medication.text
        consent = patient.post(
            f"/api/v1/patients/{patient.patient_id}/consents",
            json={"consent_type": "treatment", "purpose": f"seed-purpose-{tenant.name}-{key}"},
        )
        assert consent.status_code == 201, consent.text
        notification = patient.get("/api/v1/notifications")
        assert notification.status_code == 200 and notification.json(), notification.text
        patient.res.update(
            appointment=appointment.json()["id"],
            record=record.json()["id"],
            medication=medication.json()["id"],
            consent=consent.json()["id"],
            notification=notification.json()[0]["id"],
        )


@pytest.fixture(scope="module")
def world() -> Iterator[World]:
    engine = create_engine(TEST_DATABASE_URL, future=True)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, future=True)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        tenant_a = _new_tenant("a", ["a1", "a2"])
        tenant_b = _new_tenant("b", ["b1"])
        _seed_clinical_resources(tenant_a, hour_offset=0)
        _seed_clinical_resources(tenant_b, hour_offset=0)
        limiter.reset()
        yield World(tenant_a, tenant_b, session_factory)
    finally:
        app.dependency_overrides.pop(get_db, None)
        # Leave a fresh schema: the session-scoped `engine` fixture of other modules expects tables.
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        engine.dispose()


def fresh_patient(world: World, tenant: Tenant, label: str) -> Actor:
    """A brand-new patient so mutating tests never disturb the shared dataset."""
    limiter.reset()
    patient = Actor(f"{tenant.name}-{label}", f"{label}-{uuid.uuid4().hex[:8]}@phase1.example")
    response = patient.post(
        "/api/v1/patients/register",
        json={
            "clinic_id": tenant.clinic_id,
            "full_name": f"Patient {label}",
            "email": patient.email,
            "password": PASSWORD,
        },
        csrf=False,
    )
    assert response.status_code == 201, response.text
    patient.load_identity()
    return patient
