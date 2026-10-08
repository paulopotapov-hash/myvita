"""
Phase 1 — security validation across the whole API surface.

Covers authentication, session handling, CSRF, the role/permission matrix,
cross-tenant and cross-patient (IDOR) isolation, audit logging and error
behaviour, using the synthetic two-clinic dataset from tests/phase1_world.py.
Backend authorization is treated as the single source of truth here.
"""

from __future__ import annotations

import itertools
import json
import re
import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.core.config import settings
from app.core.database import get_db
from app.main import app
from app.models import (
    Appointment,
    AuditAction,
    AuditLog,
    AuditResult,
    Consent,
    ConsentStatus,
    MedicalRecord,
    Medication,
    MedicationStatus,
    Notification,
    Patient,
    Staff,
    User,
)
from tests.phase1_world import PASSWORD, RECORD_MARKER, Actor, Tenant, World, fresh_patient

UNSAFE = {"POST", "PATCH", "PUT", "DELETE"}
PUBLIC_ROUTES = {
    ("GET", "/health"),
    ("GET", "/ready"),
    ("GET", "/metrics"),
    ("GET", "/api/v1/config/public"),
    ("GET", "/api/v1/clinics"),
    ("GET", "/api/v1/clinics/{clinic_id}"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/clinics"),
    ("POST", "/api/v1/patients/register"),
    ("POST", "/api/v1/invitations/preview"),
    ("POST", "/api/v1/invitations/accept"),
}
_slots = itertools.count()


def _slot() -> str:
    """A unique future start time so appointment conflicts never pollute a matrix row."""
    return (datetime(2040, 1, 1, tzinfo=UTC) + timedelta(hours=next(_slots))).isoformat()


def _path(template: str) -> str:
    return re.sub(r"\{[^}]+\}", lambda _m: str(uuid.uuid4()), template)


def _api_routes() -> list[tuple[str, str]]:
    # OpenAPI is used because newer FastAPI exposes included routers lazily in app.routes.
    return [
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
        if method.upper() in {"GET", "POST", "PATCH", "PUT", "DELETE"}
    ]


def _audit_rows(world: World, **filters) -> list[AuditLog]:
    with world.db() as db:
        query = select(AuditLog)
        for column, value in filters.items():
            query = query.where(getattr(AuditLog, column) == value)
        return list(db.scalars(query.order_by(AuditLog.timestamp)))


# --------------------------------------------------------------------------
# 5. Authentication
# --------------------------------------------------------------------------


def test_every_role_authenticates_with_correct_identity(world: World):
    for tenant in (world.a, world.b):
        expected = [
            (tenant.admin, "clinic_admin", None),
            (tenant.doctor, "staff", "doctor"),
            (tenant.nurse, "staff", "nurse"),
            (tenant.staff_admin, "staff", "admin"),
            *[(p, "patient", None) for p in tenant.patients.values()],
        ]
        for actor, role, staff_role in expected:
            session = Actor(actor.key, actor.email)
            response = session.login()
            assert response.status_code == 200, (actor.key, response.text)
            body = response.json()
            assert set(body) <= {"id", "email", "full_name", "role", "clinic_id", "staff_role", "patient_id"}
            me = session.get("/api/v1/auth/me").json()
            assert me["role"] == role and me["staff_role"] == staff_role, actor.key
            assert me["clinic_id"] == tenant.clinic_id and me["email"] == actor.email
            assert (me["patient_id"] is not None) == (role == "patient")
            assert session.session_token and session.csrf_token
            assert session.session_token not in response.text and session.csrf_token not in response.text


def test_session_and_csrf_cookie_attributes(world: World):
    actor = Actor("cookie-check", world.a.doctor.email)
    response = actor.login()
    cookies = {c.split("=", 1)[0]: c for c in response.headers.get_list("set-cookie")}
    session_cookie, csrf_cookie = cookies[settings.COOKIE_NAME], cookies[settings.CSRF_COOKIE_NAME]
    assert "httponly" in session_cookie.lower()
    assert "httponly" not in csrf_cookie.lower()
    for cookie in (session_cookie, csrf_cookie):
        assert f"samesite={settings.COOKIE_SAMESITE}" in cookie.lower()
        assert "path=/" in cookie.lower()
        assert ("secure" in cookie.lower()) == settings.COOKIE_SECURE
    assert actor.session_token != actor.csrf_token
    assert not actor.csrf_token.startswith("eyJ"), "CSRF cookie must not be a JWT"


@pytest.mark.parametrize(
    "email,password",
    [("clinic-admin-a@phase1.example", "Wrong-Password-1!"), ("nobody@phase1.example", PASSWORD)],
)
def test_bad_credentials_are_indistinguishable(email: str, password: str):
    anon = Actor("anon", email)
    response = anon.login(password)
    assert response.status_code == 401
    assert response.json() == {"detail": "Email ou palavra-passe incorretos."}
    assert settings.COOKIE_NAME not in response.headers.get("set-cookie", "")


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"email": "a@phase1.example"},
        {"password": "x"},
        {"email": "not-an-email", "password": "x"},
        {"email": "a@phase1.example", "password": ""},
        {"email": "a@phase1.example", "password": "x" * 129},
        {"email": "a" * 250 + "@phase1.example", "password": "x"},
        {"email": "a@phase1.example", "password": "x", "role": "clinic_admin"},
        {"email": ["a@phase1.example"], "password": "x"},
        "just a string",
        None,
    ],
)
def test_malformed_login_requests_are_rejected_cleanly(payload):
    response = Actor("anon").post("/api/v1/auth/login", json=payload, csrf=False)
    assert response.status_code == 422
    assert settings.COOKIE_NAME not in response.headers.get("set-cookie", "")


def test_login_with_non_json_body_is_rejected():
    anon = Actor("anon")
    response = anon.client.post(
        "/api/v1/auth/login", content=b"email=a&password=b", headers={"content-type": "text/plain"}
    )
    assert response.status_code == 422


def test_inactive_user_cannot_log_in_and_live_session_is_revoked(world: World):
    patient = fresh_patient(world, world.a, "inactive")
    assert patient.get("/api/v1/auth/me").status_code == 200
    deactivated = world.a.admin.post(f"/api/v1/patients/{patient.patient_id}/deactivate")
    assert deactivated.status_code == 200 and deactivated.json()["is_active"] is False
    assert patient.get("/api/v1/auth/me").status_code == 401
    assert Actor("again", patient.email).login().status_code == 401
    with world.db() as db:
        assert db.get(User, patient.user_id).is_active is False


# --------------------------------------------------------------------------
# 5. Session behaviour
# --------------------------------------------------------------------------


def _forged(user_id: str, *, epoch: int, role: str = "patient", clinic_id: str | None = None, **claims):
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "clinic_id": clinic_id,
        "role": role,
        "epoch": epoch,
        "iat": now,
        "exp": now + timedelta(minutes=5),
        **claims,
    }
    return payload


def _with_token(token: str) -> Actor:
    actor = Actor("forged")
    actor.client.cookies.set(settings.COOKIE_NAME, token)
    return actor


def test_logout_revokes_the_session_and_clears_cookies(world: World):
    actor = Actor("logout", world.a.nurse.email)
    actor.login()
    old_session, old_csrf = actor.session_token, actor.csrf_token
    response = actor.post("/api/v1/auth/logout")
    assert response.status_code == 204
    cleared = " ".join(response.headers.get_list("set-cookie")).lower()
    assert settings.COOKIE_NAME in cleared and "max-age=0" in cleared

    replay = Actor("replay")
    replay.client.cookies.set(settings.COOKIE_NAME, old_session)
    replay.client.cookies.set(settings.CSRF_COOKIE_NAME, old_csrf)
    assert replay.get("/api/v1/auth/me").status_code == 401
    assert replay.post(f"/api/v1/notifications/{uuid.uuid4()}/read").status_code == 401
    assert actor.get("/api/v1/auth/me").status_code == 401
    world.a.nurse.login()  # logout bumps token_epoch for every session of this user; restore the shared identity


def test_invalid_and_tampered_sessions_are_rejected(world: World):
    patient = world.a.patients["a1"]
    victim = world.a.admin
    key = settings.JWT_SECRET_KEY
    with world.db() as db:
        epoch = db.get(User, patient.user_id).token_epoch
    claims = _forged(patient.user_id, epoch=epoch, clinic_id=world.a.clinic_id)

    bad_tokens = {
        "garbage": "not-a-jwt",
        "empty-ish": "a.b.c",
        "expired": jwt.encode({**claims, "exp": datetime.now(UTC) - timedelta(minutes=1)}, key, "HS256"),
        "wrong-secret": jwt.encode(claims, "x" * 64, "HS256"),
        "alg-none": jwt.encode(claims, key=None, algorithm="none"),
        "stale-epoch": jwt.encode({**claims, "epoch": epoch - 1}, key, "HS256"),
        "unknown-user": jwt.encode({**claims, "sub": str(uuid.uuid4())}, key, "HS256"),
        "no-epoch": jwt.encode({k: v for k, v in claims.items() if k != "epoch"}, key, "HS256"),
    }
    for name, token in bad_tokens.items():
        response = _with_token(token).get("/api/v1/auth/me")
        assert response.status_code == 401, name
    assert Actor("none").get("/api/v1/auth/me").status_code == 401
    assert victim.get("/api/v1/auth/me").status_code == 200


def test_server_ignores_role_and_clinic_claims_inside_the_token(world: World):
    patient = world.a.patients["a1"]
    with world.db() as db:
        epoch = db.get(User, patient.user_id).token_epoch
    token = jwt.encode(
        _forged(patient.user_id, epoch=epoch, role="clinic_admin", clinic_id=world.b.clinic_id),
        settings.JWT_SECRET_KEY,
        "HS256",
    )
    forged = _with_token(token)
    forged.client.cookies.set(settings.CSRF_COOKIE_NAME, patient.csrf_token)
    me = forged.get("/api/v1/auth/me").json()
    assert me["role"] == "patient" and me["clinic_id"] == world.a.clinic_id
    assert forged.get(f"/api/v1/patients/{world.b.patients['b1'].patient_id}").status_code == 404
    assert forged.get("/api/v1/patients").status_code == 403
    assert forged.post("/api/v1/staff", json={}).status_code == 403


def test_privilege_changes_bump_token_epoch_and_revoke_sessions(world: World):
    doctor_session = Actor("epoch", world.a.doctor.email)
    doctor_session.login()
    with world.db() as db:
        before = db.get(User, doctor_session.user_id).token_epoch
    changed = world.a.admin.patch(
        f"/api/v1/staff/{world.a.doctor.staff_id}/role",
        json={"staff_role": "doctor", "specialty": "Phase1 cardio"},
    )
    assert changed.status_code == 200
    with world.db() as db:
        assert db.get(User, doctor_session.user_id).token_epoch == before + 1
    assert doctor_session.get("/api/v1/auth/me").status_code == 401
    world.a.doctor.login()  # restore the shared identity


def test_password_change_revokes_old_sessions_but_keeps_current_one(world: World):
    patient = fresh_patient(world, world.a, "pwchange")
    other_device = Actor("device2", patient.email)
    other_device.login()
    new_password = "Phase1-Changed-Pass-7!"
    wrong = patient.post(
        "/api/v1/auth/change-password", json={"current_password": "nope-nope-1", "new_password": new_password}
    )
    assert wrong.status_code == 400
    ok = patient.post(
        "/api/v1/auth/change-password", json={"current_password": PASSWORD, "new_password": new_password}
    )
    assert ok.status_code == 204
    assert patient.get("/api/v1/auth/me").status_code == 200
    assert other_device.get("/api/v1/auth/me").status_code == 401
    assert Actor("old", patient.email).login(PASSWORD).status_code == 401
    assert Actor("new", patient.email).login(new_password).status_code == 200


# --------------------------------------------------------------------------
# 6. CSRF
# --------------------------------------------------------------------------


def _csrf_target(world: World) -> tuple[Actor, str]:
    patient = world.a.patients["a1"]
    return patient, f"/api/v1/notifications/{patient.res['notification']}/read"


def test_csrf_rejections_and_acceptance(world: World):
    patient, path = _csrf_target(world)
    other = world.a.patients["a2"]
    session = Actor("csrf", patient.email)
    session.login()
    token = session.csrf_token

    assert session.post(path, csrf=False).status_code == 403
    assert session.post(path, csrf="totally-wrong").status_code == 403
    assert session.post(path, csrf=other.csrf_token).status_code == 403  # another session's token in header
    assert session.post(path, csrf=token + "x").status_code == 403  # header differs from cookie

    swapped = Actor("csrf-swapped", patient.email)
    swapped.login()
    swapped.client.cookies.set(settings.CSRF_COOKIE_NAME, other.csrf_token)
    assert swapped.post(path, csrf=other.csrf_token).status_code == 403  # cookie+header match, wrong session

    no_cookie = Actor("csrf-nocookie", patient.email)
    no_cookie.login()
    header = no_cookie.csrf_token
    no_cookie.client.cookies.delete(settings.CSRF_COOKIE_NAME)
    assert no_cookie.post(path, csrf=header).status_code == 403  # header without cookie

    origin = settings.CORS_ORIGINS[0]
    assert session.post(path, headers={"Origin": "https://evil.example"}).status_code == 403
    assert session.post(path, headers={"Origin": "null"}).status_code == 403
    assert session.post(path, headers={"Origin": origin}).status_code == 200
    assert session.post(path).status_code == 200  # no Origin header (non-browser/same-origin client)


def test_safe_methods_do_not_need_csrf_and_unsafe_methods_always_do(world: World):
    patient = world.a.patients["a1"]
    assert patient.get("/api/v1/auth/me", csrf=False).status_code == 200
    assert patient.get("/api/v1/notifications", csrf=False).status_code == 200
    preflight = patient.call(
        "OPTIONS",
        "/api/v1/notifications/x/read",
        csrf=False,
        headers={"Origin": settings.CORS_ORIGINS[0], "Access-Control-Request-Method": "POST"},
    )
    assert preflight.status_code == 200  # preflight never needs a session or CSRF token
    for method in ("PUT", "DELETE"):
        response = patient.call(method, f"/api/v1/patients/{patient.patient_id}", {})
        assert response.status_code == 405, "no PUT/DELETE routes may exist"
    for method, path in _api_routes():
        assert method not in {"PUT", "DELETE"}, f"{method} {path} widens the CSRF surface"


def test_every_state_changing_route_enforces_csrf_for_authenticated_callers(world: World):
    admin = Actor("csrf-sweep", world.a.admin.email)
    admin.login()
    checked = 0
    for method, template in _api_routes():
        if method not in UNSAFE or (method, template) in PUBLIC_ROUTES:
            continue
        response = admin.call(method, _path(template), json={}, csrf=False)
        assert response.status_code == 403, (method, template, response.status_code, response.text)
        assert "CSRF" in response.json()["detail"], (method, template)
        checked += 1
    assert checked >= 20
    assert admin.get("/api/v1/auth/me").status_code == 200


def test_csrf_failures_are_audited_without_the_token(world: World):
    patient, path = _csrf_target(world)
    leaked = "csrf-probe-" + uuid.uuid4().hex
    before = len(_audit_rows(world, action=AuditAction.CSRF_FAILURE, actor_user_id=patient.user_id))
    assert patient.post(path, csrf=leaked).status_code == 403
    rows = _audit_rows(world, action=AuditAction.CSRF_FAILURE, actor_user_id=patient.user_id)
    assert len(rows) == before + 1
    assert rows[-1].result == AuditResult.DENIED and str(rows[-1].clinic_id) == world.a.clinic_id
    assert leaked not in json.dumps(rows[-1].event_metadata)


# --------------------------------------------------------------------------
# Default-deny sweep: every non-public route requires authentication
# --------------------------------------------------------------------------


def test_every_non_public_route_rejects_anonymous_callers():
    anon = Actor("anon")
    checked = 0
    for method, template in _api_routes():
        if (method, template) in PUBLIC_ROUTES:
            continue
        response = anon.call(method, _path(template), json={}, csrf=False)
        assert response.status_code == 401, (method, template, response.status_code)
        checked += 1
    assert checked >= 30


# --------------------------------------------------------------------------
# 7. Role / permission matrix (direct API, backend is the source of truth)
# --------------------------------------------------------------------------

ROLES = ("clinic_admin", "doctor", "nurse", "staff_admin", "patient_self", "patient_other", "anon")


def _actors(world: World) -> dict[str, Actor]:
    t = world.a
    return {
        "clinic_admin": t.admin,
        "doctor": t.doctor,
        "nurse": t.nurse,
        "staff_admin": t.staff_admin,
        "patient_self": t.patients["a1"],
        "patient_other": t.patients["a2"],
        "anon": Actor("anon"),
    }


def _rows(world: World):
    a1 = world.a.patients["a1"]
    pid, res = a1.patient_id, a1.res
    doc = world.a.doctor
    # role order:        CA   DOC  NUR  SA   P1   P2   anon
    return [
        ("me", "GET", "/api/v1/auth/me", None, (200, 200, 200, 200, 200, 200, 401)),
        ("patient directory", "GET", "/api/v1/patients", None, (200, 200, 200, 200, 403, 403, 401)),
        ("patient detail", "GET", f"/api/v1/patients/{pid}", None, (403, 200, 200, 403, 200, 404, 401)),
        (
            "patient phone update",
            "PATCH",
            f"/api/v1/patients/{pid}",
            {"phone": "910000000"},
            (403, 200, 200, 403, 200, 404, 401),
        ),
        (
            "patient demographics by patient",
            "PATCH",
            f"/api/v1/patients/{pid}",
            {"national_health_number": "1"},
            (403, 200, 200, 403, 403, 404, 401),
        ),
        (
            "patient deactivate",
            "POST",
            f"/api/v1/patients/{pid}/deactivate",
            None,
            (None, 403, 403, 403, 403, 403, 401),
        ),
        (
            "record list",
            "GET",
            f"/api/v1/patients/{pid}/medical-records",
            None,
            (403, 200, 200, 403, 200, 404, 401),
        ),
        (
            "record create",
            "POST",
            f"/api/v1/patients/{pid}/medical-records",
            {"title": "t", "content": "c"},
            (403, 201, 201, 403, 404, 404, 401),
        ),
        (
            "record detail",
            "GET",
            f"/api/v1/medical-records/{res['record']}",
            None,
            (403, 200, 200, 403, 200, 404, 401),
        ),
        (
            "record revisions",
            "GET",
            f"/api/v1/medical-records/{res['record']}/revisions",
            None,
            (403, 200, 200, 403, 200, 404, 401),
        ),
        (
            "record update (stale version)",
            "PATCH",
            f"/api/v1/medical-records/{res['record']}",
            {"title": "t", "content": "c", "expected_version": 999},
            (403, 409, 409, 403, 404, 404, 401),
        ),
        (
            "medication list",
            "GET",
            f"/api/v1/patients/{pid}/medications",
            None,
            (403, 200, 200, 403, 200, 404, 401),
        ),
        (
            "medication create",
            "POST",
            f"/api/v1/patients/{pid}/medications",
            {"name": "M", "dosage": "1 mg", "start_date": "2031-01-01"},
            (403, 201, 201, 403, 404, 404, 401),
        ),
        (
            "medication detail",
            "GET",
            f"/api/v1/medications/{res['medication']}",
            None,
            (403, 200, 200, 403, 200, 404, 401),
        ),
        (
            "medication update",
            "PATCH",
            f"/api/v1/medications/{res['medication']}",
            {"instructions": "after food"},
            (403, 200, 200, 403, 404, 404, 401),
        ),
        (
            "medication deactivate",
            "POST",
            f"/api/v1/medications/{res['medication']}/deactivate",
            None,
            (403, None, None, 403, 404, 404, 401),
        ),
        (
            "consent list",
            "GET",
            f"/api/v1/patients/{pid}/consents",
            None,
            (403, 200, 200, 403, 200, 404, 401),
        ),
        (
            "consent grant",
            "POST",
            f"/api/v1/patients/{pid}/consents",
            lambda: {"consent_type": "research", "purpose": f"matrix-{uuid.uuid4().hex[:6]}"},
            (403, 403, 403, 403, 201, 403, 401),
        ),
        (
            "consent detail",
            "GET",
            f"/api/v1/consents/{res['consent']}",
            None,
            (403, 200, 200, 403, 200, 404, 401),
        ),
        (
            "consent revoke",
            "POST",
            f"/api/v1/consents/{res['consent']}/revoke",
            None,
            (403, 403, 403, 403, None, 403, 401),
        ),
        ("appointment list", "GET", "/api/v1/appointments", None, (200, 200, 200, 200, 200, 200, 401)),
        (
            "appointment detail",
            "GET",
            f"/api/v1/appointments/{res['appointment']}",
            None,
            (200, 200, 200, 200, 200, 404, 401),
        ),
        (
            "appointment create",
            "POST",
            "/api/v1/appointments",
            lambda: {"patient_id": pid, "staff_id": doc.staff_id, "scheduled_at": _slot()},
            (201, 201, 201, 201, 403, 403, 401),
        ),
        (
            "appointment update",
            "PATCH",
            f"/api/v1/appointments/{res['appointment']}",
            {"duration_minutes": 30},
            (200, 200, 200, 200, 403, 403, 401),
        ),
        (
            "appointment cancel",
            "POST",
            f"/api/v1/appointments/{res['appointment']}/cancel",
            None,
            (None, None, None, None, 403, 403, 401),
        ),
        ("staff directory", "GET", "/api/v1/staff", None, (200, 200, 200, 200, 200, 200, 401)),
        (
            "staff create",
            "POST",
            "/api/v1/staff",
            lambda: {
                "full_name": "Matrix Nurse",
                "email": f"m-{uuid.uuid4().hex[:8]}@phase1.example",
                "password": PASSWORD,
                "staff_role": "nurse",
            },
            (201, 403, 403, 403, 403, 403, 401),
        ),
        (
            "staff deactivate",
            "POST",
            f"/api/v1/staff/{world.a.nurse.staff_id}/deactivate",
            None,
            (None, 403, 403, 403, 403, 403, 401),
        ),
        (
            "staff activate",
            "POST",
            f"/api/v1/staff/{world.a.nurse.staff_id}/activate",
            None,
            (200, 403, 403, 403, 403, 403, 401),
        ),
        (
            "staff role change",
            "PATCH",
            f"/api/v1/staff/{world.a.nurse.staff_id}/role",
            {"staff_role": "nurse"},
            (None, 403, 403, 403, 403, 403, 401),
        ),
        (
            "staff invitation",
            "POST",
            "/api/v1/invitations/staff",
            lambda: {
                "email": f"i-{uuid.uuid4().hex[:8]}@phase1.example",
                "full_name": "Invited Staff",
                "staff_role": "nurse",
            },
            (201, 403, 403, 403, 403, 403, 401),
        ),
        (
            "patient invitation",
            "POST",
            "/api/v1/invitations/patients",
            lambda: {"email": f"i-{uuid.uuid4().hex[:8]}@phase1.example", "full_name": "Invited Patient"},
            (201, 201, 201, 403, 403, 403, 401),
        ),
        ("notifications list", "GET", "/api/v1/notifications", None, (200, 200, 200, 200, 200, 200, 401)),
        (
            "notification mark read",
            "POST",
            f"/api/v1/notifications/{res['notification']}/read",
            None,
            (404, 404, 404, 404, 200, 404, 401),
        ),
    ]


def test_role_permission_matrix_is_enforced_by_the_backend(world: World):
    actors = _actors(world)
    failures: list[str] = []
    cells = 0
    for name, method, path, body, expected in _rows(world):
        for role, want in zip(ROLES, expected, strict=True):
            if want is None:
                continue
            payload = body() if callable(body) else body
            response = actors[role].call(method, path, payload)
            cells += 1
            if response.status_code != want:
                failures.append(
                    f"{name} [{role}] expected {want} got {response.status_code}: {response.text[:120]}"
                )
    assert cells > 200
    assert not failures, "\n".join(failures)
    # leave the shared nurse in a known state for later tests
    world.a.admin.post(f"/api/v1/staff/{world.a.nurse.staff_id}/activate")


def test_patient_never_sees_staff_only_or_administrative_data(world: World):
    patient = world.a.patients["a1"]
    own = patient.get(f"/api/v1/patients/{patient.patient_id}").json()
    assert set(own) == {
        "id",
        "clinic_id",
        "full_name",
        "birth_date",
        "phone",
        "national_health_number",
        "is_active",
    }
    for path in ("/api/v1/patients", "/api/v1/invitations/staff"):
        assert patient.get(path).status_code in {403, 405}
    listing = patient.get("/api/v1/appointments").json()
    assert patient.res["appointment"] in [a["id"] for a in listing]
    assert all(a["patient_id"] == patient.patient_id for a in listing)
    blob = " ".join(
        patient.get(p).text
        for p in (
            "/api/v1/appointments",
            "/api/v1/notifications",
            "/api/v1/staff",
            f"/api/v1/patients/{patient.patient_id}",
        )
    )
    for foreign in (world.a.patients["a2"], world.b.patients["b1"]):
        assert foreign.patient_id not in blob and foreign.user_id not in blob
        assert foreign.email not in blob
    assert world.b.clinic_id not in blob


def test_administrative_roles_cannot_read_clinical_content_or_appointment_reasons(world: World):
    a1 = world.a.patients["a1"]
    for actor in (world.a.admin, world.a.staff_admin):
        listing = actor.get("/api/v1/appointments").json()
        assert listing and all(item["reason"] is None for item in listing)
        detail = actor.get(f"/api/v1/appointments/{a1.res['appointment']}").json()
        assert detail["reason"] is None
        for suffix in ("medical-records", "medications", "consents"):
            assert actor.get(f"/api/v1/patients/{a1.patient_id}/{suffix}").status_code == 403
        denied = actor.post(
            "/api/v1/appointments",
            json={
                "patient_id": a1.patient_id,
                "staff_id": world.a.doctor.staff_id,
                "scheduled_at": _slot(),
                "reason": "x",
            },
        )
        assert denied.status_code == 403
    doctor_view = world.a.doctor.get(f"/api/v1/appointments/{a1.res['appointment']}").json()
    assert doctor_view["reason"] == "seed-reason-a-a1"


# --------------------------------------------------------------------------
# 8. Multi-tenancy and IDOR
# --------------------------------------------------------------------------


def _attacks(victim: Tenant, key: str, ghost: bool) -> list[tuple[str, str, object]]:
    """Every id-bearing operation aimed at one victim patient's resources."""
    new = (lambda: str(uuid.uuid4())) if ghost else None

    def pick(value: str) -> str:
        return new() if new else value

    patient = victim.patients[key]
    pid, record, medication = (
        pick(patient.patient_id),
        pick(patient.res["record"]),
        pick(patient.res["medication"]),
    )
    consent, appointment = pick(patient.res["consent"]), pick(patient.res["appointment"])
    notification, staff_id = pick(patient.res["notification"]), pick(victim.nurse.staff_id)
    doctor_id = pick(victim.doctor.staff_id)
    return [
        ("GET", f"/api/v1/patients/{pid}", None),
        ("PATCH", f"/api/v1/patients/{pid}", {"phone": "000000000"}),
        ("POST", f"/api/v1/patients/{pid}/deactivate", None),
        ("GET", f"/api/v1/patients/{pid}/medical-records", None),
        ("POST", f"/api/v1/patients/{pid}/medical-records", {"title": "x", "content": "x"}),
        ("GET", f"/api/v1/medical-records/{record}", None),
        ("GET", f"/api/v1/medical-records/{record}/revisions", None),
        ("PATCH", f"/api/v1/medical-records/{record}", {"title": "x", "content": "x", "expected_version": 1}),
        ("GET", f"/api/v1/patients/{pid}/medications", None),
        (
            "POST",
            f"/api/v1/patients/{pid}/medications",
            {"name": "x", "dosage": "x", "start_date": "2031-01-01"},
        ),
        ("GET", f"/api/v1/medications/{medication}", None),
        ("PATCH", f"/api/v1/medications/{medication}", {"dosage": "999 g"}),
        ("POST", f"/api/v1/medications/{medication}/deactivate", None),
        ("GET", f"/api/v1/patients/{pid}/consents", None),
        ("POST", f"/api/v1/patients/{pid}/consents", {"consent_type": "research", "purpose": "idor"}),
        ("GET", f"/api/v1/consents/{consent}", None),
        ("POST", f"/api/v1/consents/{consent}/revoke", None),
        ("GET", f"/api/v1/appointments/{appointment}", None),
        ("PATCH", f"/api/v1/appointments/{appointment}", {"duration_minutes": 60}),
        ("POST", f"/api/v1/appointments/{appointment}/cancel", None),
        (
            "POST",
            "/api/v1/appointments",
            {"patient_id": pid, "staff_id": doctor_id, "scheduled_at": "2032-01-01T10:00:00+00:00"},
        ),
        ("POST", f"/api/v1/notifications/{notification}/read", None),
        ("POST", f"/api/v1/staff/{staff_id}/deactivate", None),
        ("POST", f"/api/v1/staff/{staff_id}/activate", None),
        ("PATCH", f"/api/v1/staff/{staff_id}/role", {"staff_role": "admin"}),
    ]


def _attack_everything(
    attackers: list[Actor], victim: Tenant, key: str, label: str, *, strict: bool = True
) -> int:
    real, ghosts = _attacks(victim, key, ghost=False), _attacks(victim, key, ghost=True)
    failures, calls = [], 0
    for attacker in attackers:
        for (method, path, body), (_, ghost_path, ghost_body) in zip(real, ghosts, strict=True):
            actual = attacker.call(method, path, body)
            ghost = attacker.call(method, ghost_path, ghost_body)
            calls += 1
            if actual.status_code < 400 or (strict and actual.status_code != ghost.status_code):
                failures.append(
                    f"{label} {attacker.key}: {method} {path} -> {actual.status_code} "
                    f"(nonexistent id -> {ghost.status_code})"
                )
            elif strict and actual.status_code == 404 and actual.json() != ghost.json():
                failures.append(
                    f"{label} {attacker.key}: {method} {path} 404 body differs from nonexistent id"
                )
    assert not failures, "\n".join(failures)
    return calls


def test_clinic_a_cannot_touch_clinic_b_and_vice_versa_by_id(world: World):
    calls = _attack_everything(world.a.everyone, world.b, "b1", "A->B")
    calls += _attack_everything(world.b.everyone, world.a, "a1", "B->A")
    calls += _attack_everything(world.b.everyone, world.a, "a2", "B->A2")
    assert calls >= 350


def test_patient_a1_cannot_touch_patient_a2_in_the_same_clinic(world: World):
    # Same clinic: denial is mandatory; the 403-vs-404 wording for existing ids is a known, low-risk
    # difference (UUIDv4 ids are unguessable) tracked in the Phase 2 report.
    a1, a2 = world.a.patients["a1"], world.a.patients["a2"]
    assert _attack_everything([a1], world.a, "a2", "A1->A2", strict=False) == len(
        _attacks(world.a, "a2", False)
    )
    assert _attack_everything([a2], world.a, "a1", "A2->A1", strict=False) > 0


def test_cross_tenant_attempts_left_victim_data_untouched(world: World):
    b1 = world.b.patients["b1"]
    a1, a2 = world.a.patients["a1"], world.a.patients["a2"]
    with world.db() as db:
        for victim_patient, tenant in ((b1, world.b), (a1, world.a), (a2, world.a)):
            res = victim_patient.res
            record = db.get(MedicalRecord, res["record"])
            assert record.version == 1 and RECORD_MARKER in record.content and record.title.startswith("Seed")
            medication = db.get(Medication, res["medication"])
            assert medication.dosage == "10 mg" and medication.status == MedicationStatus.ACTIVE
            assert db.get(Consent, res["consent"]).status == ConsentStatus.GRANTED
            if victim_patient is not a1:  # a1's own notification is read legitimately by the matrix test
                assert db.get(Notification, res["notification"]).is_read is False
            assert db.get(Appointment, res["appointment"]).duration_minutes == 30
            assert db.get(Patient, victim_patient.patient_id).phone == "910000000"
            assert db.get(User, victim_patient.user_id).is_active is True
            assert db.get(Staff, tenant.nurse.staff_id).staff_role.value == "nurse"
            assert db.get(User, tenant.nurse.user_id).is_active is True


def test_cross_tenant_ids_inside_bodies_and_mixed_requests_are_blocked(world: World):
    doctor, b1 = world.a.doctor, world.b.patients["b1"]
    a1 = world.a.patients["a1"]
    own = {"patient_id": a1.patient_id, "staff_id": doctor.staff_id}
    foreign_staff = world.b.doctor.staff_id
    when = "2032-05-05T10:00:00+00:00"
    cases = [
        ({**own, "patient_id": b1.patient_id}, 404),
        ({**own, "staff_id": foreign_staff}, 404),
        ({"patient_id": b1.patient_id, "staff_id": foreign_staff}, 404),
        ({**own, "clinic_id": world.b.clinic_id}, 422),
    ]
    for body, status in cases:
        assert doctor.post("/api/v1/appointments", json={**body, "scheduled_at": when}).status_code == status

    mine = doctor.post(
        "/api/v1/appointments", json={**own, "scheduled_at": "2032-05-06T10:00:00+00:00"}
    ).json()
    for patch in ({"patient_id": b1.patient_id}, {"staff_id": foreign_staff}):
        assert doctor.patch(f"/api/v1/appointments/{mine['id']}", json=patch).status_code == 404
    unchanged = doctor.get(f"/api/v1/appointments/{mine['id']}").json()
    assert unchanged["patient_id"] == a1.patient_id and unchanged["staff_id"] == doctor.staff_id

    injections = [
        (
            f"/api/v1/patients/{a1.patient_id}/medical-records",
            {"title": "t", "content": "c", "clinic_id": world.b.clinic_id},
        ),
        (
            f"/api/v1/patients/{a1.patient_id}/medical-records",
            {"title": "t", "content": "c", "patient_id": b1.patient_id},
        ),
        (
            f"/api/v1/patients/{a1.patient_id}/medications",
            {"name": "n", "dosage": "d", "start_date": "2031-01-01", "clinic_id": world.b.clinic_id},
        ),
        (
            f"/api/v1/patients/{a1.patient_id}/medications",
            {"name": "n", "dosage": "d", "start_date": "2031-01-01", "prescribed_by_staff_id": foreign_staff},
        ),
    ]
    for path, body in injections:
        assert doctor.post(path, json=body).status_code == 422, (path, body)
    assert (
        a1.patch(
            f"/api/v1/patients/{a1.patient_id}", json={"phone": "1", "clinic_id": world.b.clinic_id}
        ).status_code
        == 422
    )
    assert (
        a1.post(
            f"/api/v1/patients/{a1.patient_id}/consents",
            json={
                "consent_type": "research",
                "purpose": "x",
                "clinic_id": world.b.clinic_id,
                "patient_id": b1.patient_id,
            },
        ).status_code
        == 422
    )


def test_list_endpoints_ignore_foreign_scope_in_query_strings(world: World):
    foreign = {
        world.b.clinic_id,
        world.b.patients["b1"].patient_id,
        world.b.patients["b1"].res["appointment"],
        world.b.doctor.staff_id,
        world.b.patients["b1"].res["record"],
    }
    query = f"?clinic_id={world.b.clinic_id}&patient_id={world.b.patients['b1'].patient_id}&staff_id={world.b.doctor.staff_id}"
    for actor in world.a.everyone:
        for path in ("/api/v1/appointments", "/api/v1/patients", "/api/v1/staff", "/api/v1/notifications"):
            response = actor.get(path + query)
            if response.status_code != 200:
                assert response.status_code == 403
                continue
            assert not any(value in response.text for value in foreign), (actor.key, path)
    for actor in world.b.everyone:
        for path in ("/api/v1/appointments", "/api/v1/patients", "/api/v1/staff", "/api/v1/notifications"):
            response = actor.get(path + f"?clinic_id={world.a.clinic_id}")
            if response.status_code == 200:
                assert (
                    world.a.clinic_id not in response.text
                    and world.a.patients["a1"].patient_id not in response.text
                )


def test_admin_and_staff_listings_are_strictly_tenant_scoped(world: World):
    for tenant, other in ((world.a, world.b), (world.b, world.a)):
        for actor in (tenant.admin, tenant.doctor, tenant.nurse, tenant.staff_admin):
            for path in ("/api/v1/patients", "/api/v1/staff", "/api/v1/appointments"):
                body = actor.get(path).json()
                assert body and all(item["clinic_id"] == tenant.clinic_id for item in body), (actor.key, path)
        names = {s["id"] for s in tenant.admin.get("/api/v1/staff").json()}
        assert {tenant.doctor.staff_id, tenant.nurse.staff_id, tenant.staff_admin.staff_id} <= names
        assert other.doctor.staff_id not in names


def test_deactivate_and_role_change_by_clinic_admin_are_tenant_scoped(world: World):
    victim = world.b.nurse
    for path, method, body in (
        (f"/api/v1/staff/{victim.staff_id}/deactivate", "POST", None),
        (f"/api/v1/staff/{victim.staff_id}/role", "PATCH", {"staff_role": "doctor"}),
        (f"/api/v1/patients/{world.b.patients['b1'].patient_id}/deactivate", "POST", None),
    ):
        assert world.a.admin.call(method, path, body).status_code == 404
    assert victim.get("/api/v1/auth/me").status_code == 200
    assert world.b.patients["b1"].get("/api/v1/auth/me").status_code == 200


# --------------------------------------------------------------------------
# 16. Audit logging
# --------------------------------------------------------------------------


def test_security_and_clinical_events_are_audited_with_correct_context(world: World):
    patient = fresh_patient(world, world.a, "audit")
    doctor = world.a.doctor
    assert Actor("fail", patient.email).login("Wrong-Audit-Pass-1!").status_code == 401
    assert Actor("fail2", "ghost-audit@phase1.example").login("Wrong-Audit-Pass-1!").status_code == 401
    assert patient.get("/api/v1/patients").status_code == 403  # permission denied
    appointment = doctor.post(
        "/api/v1/appointments",
        json={
            "patient_id": patient.patient_id,
            "staff_id": doctor.staff_id,
            "scheduled_at": _slot(),
            "reason": "audit-reason",
        },
    ).json()
    doctor.get(f"/api/v1/appointments/{appointment['id']}")
    doctor.patch(f"/api/v1/appointments/{appointment['id']}", json={"status": "confirmed"})
    doctor.post(f"/api/v1/appointments/{appointment['id']}/cancel")
    record = doctor.post(
        f"/api/v1/patients/{patient.patient_id}/medical-records",
        json={"title": "Audit", "content": f"{RECORD_MARKER}-audit"},
    ).json()
    doctor.get(f"/api/v1/medical-records/{record['id']}")
    doctor.patch(
        f"/api/v1/medical-records/{record['id']}",
        json={"title": "Audit2", "content": f"{RECORD_MARKER}-audit2", "expected_version": 1},
    )
    medication = doctor.post(
        f"/api/v1/patients/{patient.patient_id}/medications",
        json={"name": "Auditol", "dosage": "5 mg", "start_date": "2031-01-01"},
    ).json()
    doctor.patch(f"/api/v1/medications/{medication['id']}", json={"instructions": "audit"})
    doctor.post(f"/api/v1/medications/{medication['id']}/deactivate")
    consent = patient.post(
        f"/api/v1/patients/{patient.patient_id}/consents",
        json={"consent_type": "treatment", "purpose": "audit"},
    ).json()
    doctor.get(f"/api/v1/consents/{consent['id']}")
    patient.post(f"/api/v1/consents/{consent['id']}/revoke")
    notification = patient.get("/api/v1/notifications").json()[0]
    patient.post(f"/api/v1/notifications/{notification['id']}/read")
    patient.post("/api/v1/auth/logout")

    def has(
        action: AuditAction,
        *,
        resource_id: str | None = None,
        actor: Actor | None = None,
        result=AuditResult.SUCCESS,
    ):
        filters = {"action": action, "result": result}
        if resource_id:
            filters["resource_id"] = resource_id
        if actor:
            filters["actor_user_id"] = actor.user_id
        rows = _audit_rows(world, **filters)
        assert rows, f"missing audit event {action.value} {resource_id or ''}"
        return rows[-1]

    assert [
        r.action
        for r in _audit_rows(world, actor_email=patient.email)
        if r.action == AuditAction.LOGIN_FAILURE
    ]
    ghost = _audit_rows(world, actor_email="ghost-audit@phase1.example")
    assert ghost and ghost[-1].action == AuditAction.LOGIN_FAILURE and ghost[-1].actor_user_id is None
    has(AuditAction.PATIENT_CREATED, resource_id=patient.patient_id, actor=patient)
    has(AuditAction.PERMISSION_DENIED, actor=patient, result=AuditResult.DENIED)
    has(AuditAction.LOGOUT, actor=patient)
    for action, resource, actor in (
        (AuditAction.APPOINTMENT_CREATED, appointment["id"], doctor),
        (AuditAction.STAFF_VIEWED_APPOINTMENT, appointment["id"], doctor),
        (AuditAction.APPOINTMENT_UPDATED, appointment["id"], doctor),
        (AuditAction.APPOINTMENT_CANCELLED, appointment["id"], doctor),
        (AuditAction.MEDICAL_RECORD_CREATED, record["id"], doctor),
        (AuditAction.MEDICAL_RECORD_VIEWED, record["id"], doctor),
        (AuditAction.MEDICAL_RECORD_UPDATED, record["id"], doctor),
        (AuditAction.MEDICATION_CREATED, medication["id"], doctor),
        (AuditAction.MEDICATION_UPDATED, medication["id"], doctor),
        (AuditAction.MEDICATION_DEACTIVATED, medication["id"], doctor),
        (AuditAction.CONSENT_GRANTED, consent["id"], patient),
        (AuditAction.CONSENT_VIEWED, consent["id"], doctor),
        (AuditAction.CONSENT_REVOKED, consent["id"], patient),
        (AuditAction.NOTIFICATION_READ, notification["id"], patient),
    ):
        row = has(action, resource_id=resource, actor=actor)
        assert str(row.clinic_id) == world.a.clinic_id, action

    for action in (
        AuditAction.LOGIN_SUCCESS,
        AuditAction.STAFF_CREATED,
        AuditAction.CLINIC_CREATED,
        AuditAction.INVITATION_CREATED,
    ):
        assert _audit_rows(world, action=action), action


def test_audit_trail_contains_no_secrets_or_clinical_content(world: World):
    wrong_password = "Wrong-Secret-Probe-1!"
    Actor("probe", world.a.doctor.email).login(wrong_password)
    tokens = []
    for tenant in (world.a, world.b):
        for actor in tenant.everyone:
            tokens += [t for t in (actor.session_token, actor.csrf_token) if t]
    with world.db() as db:
        rows = list(db.scalars(select(AuditLog)))
    assert len(rows) > 50
    dump = "\n".join(
        json.dumps(
            [r.actor_email, r.user_agent, r.ip_address, r.resource_type, r.event_metadata, r.action.value],
            default=str,
        )
        for r in rows
    )
    for forbidden in (
        PASSWORD,
        wrong_password,
        RECORD_MARKER,
        "seed-reason",
        "Seedamol",
        "eyJ",
        settings.JWT_SECRET_KEY,
        *tokens,
    ):
        assert forbidden not in dump, f"audit trail leaks {forbidden[:12]}..."


# --------------------------------------------------------------------------
# 17. API error behaviour
# --------------------------------------------------------------------------

_LEAK_MARKERS = (
    "Traceback",
    'File "',
    "/app/",
    "sqlalchemy",
    "psycopg",
    "postgresql",
    "SELECT ",
    "INSERT ",
    "hunter2",
)


def _assert_clean_error(response, *, status: int) -> None:
    assert response.status_code == status, response.text
    assert response.headers.get("x-request-id"), "request id must be present on errors"
    lowered = response.text
    for marker in _LEAK_MARKERS:
        assert marker not in lowered, f"{marker!r} leaked in {response.text[:200]}"
    assert settings.JWT_SECRET_KEY not in response.text


def test_error_statuses_are_well_formed_and_do_not_leak_internals(world: World):
    doctor, patient, admin = world.a.doctor, world.a.patients["a1"], world.a.admin
    a1_id = patient.patient_id
    _assert_clean_error(Actor("anon").get("/api/v1/auth/me"), status=401)
    _assert_clean_error(patient.get("/api/v1/patients"), status=403)
    _assert_clean_error(doctor.get(f"/api/v1/patients/{uuid.uuid4()}"), status=404)
    _assert_clean_error(doctor.get("/api/v1/patients/not-a-uuid"), status=422)
    _assert_clean_error(doctor.get("/api/v1/does-not-exist"), status=404)
    _assert_clean_error(doctor.post("/api/v1/appointments", json={"patient_id": "x"}), status=422)
    _assert_clean_error(
        admin.post(
            "/api/v1/staff",
            json={
                "full_name": "Dup",
                "email": world.a.doctor.email,
                "password": PASSWORD,
                "staff_role": "nurse",
            },
        ),
        status=400,
    )
    _assert_clean_error(
        patient.post(
            f"/api/v1/patients/{a1_id}/consents",
            json={"consent_type": "treatment", "purpose": "seed-purpose-a-a1"},
        ),
        status=409,
    )
    _assert_clean_error(
        doctor.patch(
            f"/api/v1/medical-records/{patient.res['record']}",
            json={"title": "t", "content": "c", "expected_version": 77},
        ),
        status=409,
    )
    huge = doctor.client.post(
        "/api/v1/appointments",
        content=b"{}",
        headers={"content-length": str(settings.MAX_REQUEST_BODY_BYTES + 1)},
    )
    _assert_clean_error(huge, status=413)


def test_request_ids_are_echoed_when_valid_and_replaced_when_not(world: World):
    doctor = world.a.doctor
    mine = "phase1-" + uuid.uuid4().hex
    assert doctor.get("/api/v1/auth/me", headers={"X-Request-ID": mine}).headers["x-request-id"] == mine
    bad = doctor.get("/api/v1/auth/me", headers={"X-Request-ID": "bad id\twith spaces <script>"})
    assert bad.headers["x-request-id"] != "bad id\twith spaces <script>"


def test_login_rate_limit_returns_429_and_is_audited(world: World):
    from app.core.rate_limit import limiter

    limiter.reset()
    attacker = Actor("bruteforce", "rate-limit-probe@phase1.example")
    codes = [
        attacker.client.post(
            "/api/v1/auth/login", json={"email": attacker.email, "password": "x"}
        ).status_code
        for _ in range(12)
    ]
    assert codes[:10] == [401] * 10 and set(codes[10:]) == {429}
    limited = attacker.client.post("/api/v1/auth/login", json={"email": attacker.email, "password": "x"})
    _assert_clean_error(limited, status=429)
    assert _audit_rows(world, action=AuditAction.RATE_LIMITED)
    limiter.reset()


def test_database_outage_returns_503_without_leaking_details(world: World):
    class BrokenSession:
        def get(self, *_args, **_kwargs):
            raise OperationalError(
                "SELECT * FROM users WHERE password='hunter2'", {}, Exception("postgresql://u:hunter2@db/x")
            )

        def close(self):
            pass

    def broken_db():
        yield BrokenSession()

    previous = app.dependency_overrides[get_db]
    app.dependency_overrides[get_db] = broken_db
    try:
        response = world.a.doctor.get("/api/v1/auth/me")
    finally:
        app.dependency_overrides[get_db] = previous
    _assert_clean_error(response, status=503)
    assert response.json() == {"detail": "Serviço temporariamente indisponível."}
    assert world.a.doctor.get("/api/v1/auth/me").status_code == 200


def test_unhandled_bug_returns_generic_500_with_request_id():
    async def boom():
        raise RuntimeError("secret-internal-detail /app/app/secret.py hunter2")

    app.add_api_route("/__phase1_boom", boom, methods=["GET"])
    try:
        quiet = Actor("quiet", raise_server_exceptions=False)
        response = quiet.get("/__phase1_boom")
    finally:
        app.router.routes.pop()
    _assert_clean_error(response, status=500)
    assert response.json() == {"detail": "Erro interno do servidor."}
    assert "secret-internal-detail" not in response.text
