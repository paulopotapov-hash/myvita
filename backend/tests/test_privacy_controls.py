"""
Phase 5 — technical privacy controls: log hygiene, data minimisation and the
absence of uncontrolled access paths. These tests verify engineering controls
only; they say nothing about legal compliance.
"""

from __future__ import annotations

import logging
import uuid

from app.core.config import settings
from app.main import app
from app.models import UserRole
from tests.phase1_world import Actor, World


def test_failed_login_application_logs_do_not_contain_the_attempted_email(world: World, caplog):
    unknown = f"nobody-{uuid.uuid4().hex[:8]}@privacy.example"
    with caplog.at_level(logging.DEBUG):
        assert Actor("unknown", unknown).login("Wrong-Password-1!").status_code == 401
        assert Actor("known", world.a.doctor.email).login("Wrong-Password-1!").status_code == 401
    text = "\n".join(record.getMessage() for record in caplog.records)
    assert unknown not in text and world.a.doctor.email not in text
    assert "Wrong-Password-1!" not in text


def test_request_logs_never_contain_query_strings_such_as_patient_search_terms(world: World, caplog):
    term = f"Zq{uuid.uuid4().hex[:6]}"
    with caplog.at_level(logging.DEBUG):
        assert world.a.doctor.get(f"/api/v1/patients?search={term}").status_code == 200
    # The HTTP test client itself logs full URLs, so only the application's loggers are inspected.
    app_logs = [r.getMessage() for r in caplog.records if r.name.startswith(("myvita", "uvicorn"))]
    assert any("request_completed" in line for line in app_logs)
    assert term not in "\n".join(app_logs)


def test_clinic_directory_is_not_enumerable_without_public_registration(world: World, monkeypatch):
    anon = Actor("anon")
    monkeypatch.setattr(settings, "ALLOW_PUBLIC_PATIENT_REGISTRATION", True)
    # Registration being open is not enough: no clinic is public until it is allowlisted (P2.1).
    monkeypatch.setattr(settings, "PUBLIC_CLINIC_IDS", [])
    assert anon.get("/api/v1/clinics").json() == []
    monkeypatch.setattr(settings, "PUBLIC_CLINIC_IDS", [uuid.UUID(world.a.clinic_id), uuid.UUID(world.b.clinic_id)])
    ids = {clinic["id"] for clinic in anon.get("/api/v1/clinics").json()}
    assert {world.a.clinic_id, world.b.clinic_id} <= ids

    monkeypatch.setattr(settings, "ALLOW_PUBLIC_PATIENT_REGISTRATION", False)
    assert anon.get("/api/v1/clinics").json() == []
    for actor, own, other in ((world.a.doctor, world.a, world.b), (world.b.patients["b1"], world.b, world.a)):
        visible = {clinic["id"] for clinic in actor.get("/api/v1/clinics").json()}
        assert visible == {own.clinic_id} and other.clinic_id not in visible


def test_there_is_no_platform_support_role_export_or_audit_read_surface():
    assert {role.value for role in UserRole} == {"patient", "staff", "clinic_admin"}
    for path, operations in app.openapi()["paths"].items():
        assert not any(word in path.lower() for word in ("export", "audit", "support", "admin/")), path
        assert not set(operations) & {"delete", "put"}, path


def test_list_endpoints_return_only_the_minimum_fields(world: World):
    patients = world.a.doctor.get("/api/v1/patients").json()
    assert patients and all(set(item) == {"id", "clinic_id", "full_name", "is_active"} for item in patients)
    staff = world.a.admin.get("/api/v1/staff").json()
    assert staff and all(
        set(item) == {"id", "clinic_id", "full_name", "staff_role", "specialty", "is_active"} for item in staff
    )
    me = world.a.doctor.get("/api/v1/auth/me").json()
    assert not {"hashed_password", "token_epoch", "is_active"} & set(me)


def test_login_response_matches_auth_me_so_the_spa_has_staff_role_and_patient_id(world: World):
    # Regression (Phase 6, UAT-10): login returned staff_role/patient_id as null, hiding role-dependent UI until reload.
    for actor in (world.a.doctor, world.a.nurse, world.a.admin, world.a.staff_admin, world.a.patients["a1"]):
        fresh = Actor("fresh", actor.email)
        login_body = fresh.login().json()
        assert login_body == fresh.get("/api/v1/auth/me").json(), actor.key
    doctor_login = Actor("fresh-doc", world.a.doctor.email).login().json()
    assert doctor_login["staff_role"] == "doctor"
    assert Actor("fresh-pat", world.a.patients["a1"].email).login().json()["patient_id"] == world.a.patients["a1"].patient_id
