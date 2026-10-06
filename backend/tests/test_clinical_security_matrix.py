"""
Security matrix for every clinical workflow: authentication, role
authorization, IDOR (same clinic and cross clinic), multi-tenancy, tenant
ownership immutability and audit-trail isolation.

Every actor is a real logged-in user of one of two clinics, on the real
PostgreSQL schema.
"""

from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.models import Appointment, AuditLog, MedicalRecord, Medication, Notification
from tests.clinical_support import (
    ALL_ROLES,
    Tenant,
    audit,
    book,
    grant,
    make_tenant,
    notify,
    prescribe,
    slot,
    use,
    write_record,
)

SECRET = "SECRET"
DENIED = {403, 404}


@dataclass
class Seed:
    appointment: str
    record: str
    medication: str
    consent: str
    notification: str


def _seed(client: TestClient, tenant: Tenant, tag: str) -> Seed:
    appointment = book(client, tenant, reason=f"{SECRET}-REASON-{tag}")
    record = write_record(client, tenant, f"{SECRET}-RECORD-{tag}")
    medication = prescribe(client, tenant, f"{SECRET}-MED-{tag}")
    consent = grant(client, tenant, f"{SECRET}-PURPOSE-{tag}")
    notification = notify(client, tenant, "patient", f"{SECRET}-NOTE-{tag}")
    return Seed(appointment["id"], record["id"], medication["id"], consent["id"], notification)


@dataclass
class World:
    a: Tenant
    b: Tenant
    seed_a: Seed
    seed_b: Seed


@pytest.fixture()
def world(client: TestClient) -> World:
    a = make_tenant(client, "alpha")
    b = make_tenant(client, "beta")
    return World(a, b, _seed(client, a, "A"), _seed(client, b, "B"))


def _requests(tenant: Tenant, seed: Seed) -> list[tuple[str, str, str, dict | None]]:
    """Every clinical endpoint, aimed at one tenant's resources."""
    pid = tenant.patient_id
    return [
        ("appointment detail", "GET", f"/api/v1/appointments/{seed.appointment}", None),
        ("appointment update", "PATCH", f"/api/v1/appointments/{seed.appointment}", {"duration_minutes": 55}),
        ("appointment cancel", "POST", f"/api/v1/appointments/{seed.appointment}/cancel", None),
        (
            "appointment create",
            "POST",
            "/api/v1/appointments",
            {"patient_id": pid, "staff_id": tenant.staff_ids["doctor"], "scheduled_at": slot(days=20)},
        ),
        ("record list", "GET", f"/api/v1/patients/{pid}/medical-records", None),
        (
            "record create",
            "POST",
            f"/api/v1/patients/{pid}/medical-records",
            {"title": "INJECTED", "content": "INJECTED"},
        ),
        ("record detail", "GET", f"/api/v1/medical-records/{seed.record}", None),
        (
            "record update",
            "PATCH",
            f"/api/v1/medical-records/{seed.record}",
            {"title": "INJECTED", "content": "INJECTED"},
        ),
        ("record revisions", "GET", f"/api/v1/medical-records/{seed.record}/revisions", None),
        ("medication list", "GET", f"/api/v1/patients/{pid}/medications", None),
        (
            "medication create",
            "POST",
            f"/api/v1/patients/{pid}/medications",
            {"name": "INJECTED", "dosage": "1 mg", "start_date": "2026-01-01"},
        ),
        ("medication detail", "GET", f"/api/v1/medications/{seed.medication}", None),
        ("medication update", "PATCH", f"/api/v1/medications/{seed.medication}", {"dosage": "INJECTED"}),
        ("medication deactivate", "POST", f"/api/v1/medications/{seed.medication}/deactivate", None),
        ("consent list", "GET", f"/api/v1/patients/{pid}/consents", None),
        (
            "consent create",
            "POST",
            f"/api/v1/patients/{pid}/consents",
            {"consent_type": "research", "purpose": "INJECTED"},
        ),
        ("consent detail", "GET", f"/api/v1/consents/{seed.consent}", None),
        ("consent revoke", "POST", f"/api/v1/consents/{seed.consent}/revoke", None),
        ("notification read", "POST", f"/api/v1/notifications/{seed.notification}/read", None),
    ]


def _send(client: TestClient, method: str, url: str, body: dict | None, headers: dict | None):
    return client.request(method, url, json=body, headers=headers)


def _assert_untouched(client: TestClient, tenant: Tenant, seed: Seed) -> None:
    """The tenant's own data is exactly as seeded, whatever was attempted against it."""
    tenant.act(client, "doctor")
    appointment = client.get(f"/api/v1/appointments/{seed.appointment}").json()
    assert appointment["status"] == "scheduled"
    assert appointment["duration_minutes"] == 30
    record = client.get(f"/api/v1/medical-records/{seed.record}").json()
    assert (record["version"], record["title"]) == (1, "Assessment")
    medication = client.get(f"/api/v1/medications/{seed.medication}").json()
    assert (medication["status"], medication["dosage"]) == ("active", "10 mg")
    assert len(client.get(f"/api/v1/patients/{tenant.patient_id}/medical-records").json()) == 1
    assert len(client.get(f"/api/v1/patients/{tenant.patient_id}/medications").json()) == 1
    assert len(client.get("/api/v1/appointments").json()) == 1
    tenant.act(client, "patient")
    consents = client.get(f"/api/v1/patients/{tenant.patient_id}/consents").json()
    assert [(row["id"], row["status"]) for row in consents] == [(seed.consent, "granted")]
    notifications = client.get("/api/v1/notifications").json()
    assert [(row["id"], row["is_read"]) for row in notifications] == [(seed.notification, False)]


def _db_rows(client: TestClient, model):
    with client.session_factory() as db:  # type: ignore[attr-defined]
        rows = db.query(model).all()
        for row in rows:
            db.expunge(row)
        return rows


# --- authentication -------------------------------------------------------


@pytest.mark.parametrize("kind", ["no_session", "invalid_session", "revoked_doctor", "revoked_patient"])
def test_every_clinical_endpoint_requires_a_live_session(client: TestClient, world: World, kind: str):
    headers: dict | None = None
    if kind == "no_session":
        client.cookies.clear()
    elif kind == "invalid_session":
        client.cookies.clear()
        client.cookies.set(settings.COOKIE_NAME, "not.a.jwt")
        client.cookies.set(settings.CSRF_COOKIE_NAME, "forged")
        headers = {settings.CSRF_HEADER_NAME: "forged"}
    else:
        role = kind.removeprefix("revoked_")
        headers = use(client, world.a.who[role])
        assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
        headers = use(client, world.a.who[role])  # replay the now-revoked session

    for label, method, url, body in _requests(world.a, world.seed_a):
        response = _send(client, method, url, body, headers)
        assert response.status_code == 401, f"{kind}: {label} -> {response.status_code}"
        assert SECRET not in response.text

    client.cookies.clear()
    assert client.get("/api/v1/appointments").status_code == 401
    assert client.get("/api/v1/notifications").status_code == 401


# --- authorization --------------------------------------------------------


@pytest.mark.parametrize("role", ["clinic_admin", "admin"])
def test_administrative_roles_cannot_touch_clinical_content(client: TestClient, world: World, role: str):
    headers = world.a.act(client, role)
    clinical = ("record", "medication", "consent")
    for label, method, url, body in _requests(world.a, world.seed_a):
        if label.split()[0] not in clinical:
            continue
        response = _send(client, method, url, body, headers)
        assert response.status_code == 403, f"{role}: {label} -> {response.status_code}"
        assert SECRET not in response.text
    _assert_untouched(client, world.a, world.seed_a)

    # Scheduling stays operational, but the clinical reason stays hidden and unwritable.
    world.a.act(client, role)
    detail = client.get(f"/api/v1/appointments/{world.seed_a.appointment}")
    assert detail.status_code == 200
    assert detail.json()["reason"] is None
    assert SECRET not in detail.text


def test_patient_cannot_perform_clinical_or_scheduling_writes(client: TestClient, world: World):
    headers = world.a.act(client, "patient")
    for label, method, url, body in _requests(world.a, world.seed_a):
        if method == "GET":
            continue
        if label.startswith("consent") or label.startswith("notification"):
            continue  # patient-owned actions, covered by the consent / inbox workflows
        response = _send(client, method, url, body, headers)
        expected = {403} if label.startswith("appointment") else DENIED
        assert response.status_code in expected, f"{label} -> {response.status_code}"
    world.a.act(client, "doctor")
    assert client.get(f"/api/v1/patients/{world.a.patient_id}/medical-records").json()[0]["version"] == 1
    _assert_untouched(client, world.a, world.seed_a)


@pytest.mark.parametrize("role", ["doctor", "nurse"])
def test_clinicians_cannot_grant_or_revoke_a_patients_consent(client: TestClient, world: World, role: str):
    headers = world.a.act(client, role)
    grant_attempt = client.post(
        f"/api/v1/patients/{world.a.patient_id}/consents",
        headers=headers,
        json={"consent_type": "research", "purpose": "By clinician"},
    )
    assert grant_attempt.status_code == 403
    assert client.post(f"/api/v1/consents/{world.seed_a.consent}/revoke", headers=headers).status_code == 403
    _assert_untouched(client, world.a, world.seed_a)


@pytest.mark.parametrize("role", ["doctor", "nurse", "admin", "patient"])
def test_staff_administration_is_reserved_to_the_clinic_admin(client: TestClient, world: World, role: str):
    headers = world.a.act(client, role)
    response = client.post(
        "/api/v1/staff",
        headers=headers,
        json={
            "full_name": "Intruder",
            "email": f"intruder-{role}@example.pt",
            "password": "SenhaForte123!",
            "staff_role": "doctor",
        },
    )
    assert response.status_code == 403


def test_denied_clinical_access_is_audited_under_the_actors_clinic(client: TestClient, world: World):
    world.b.act(client, "doctor")
    assert client.get(f"/api/v1/medical-records/{world.seed_a.record}").status_code == 404
    assert client.get(f"/api/v1/consents/{world.seed_a.consent}").status_code == 404
    assert client.get(f"/api/v1/appointments/{world.seed_a.appointment}").status_code == 404
    assert client.get(f"/api/v1/medications/{world.seed_a.medication}").status_code == 404
    world.a.act(client, "admin")
    assert client.get(f"/api/v1/medical-records/{world.seed_a.record}").status_code == 403

    for resource_id in (world.seed_a.record, world.seed_a.consent, world.seed_a.appointment, world.seed_a.medication):
        rows = audit(client, "permission_denied", resource_id=resource_id)
        assert rows, resource_id
        assert all(row.result.value == "denied" for row in rows)
    cross = audit(client, "permission_denied", resource_id=world.seed_a.record)
    assert {str(row.clinic_id) for row in cross} == {world.b.clinic_id, world.a.clinic_id}
    assert {str(row.actor_user_id) for row in cross} == {world.b.user_ids["doctor"], world.a.user_ids["admin"]}


# --- IDOR within one clinic ----------------------------------------------


def test_patient_cannot_reach_another_patients_data_in_the_same_clinic(client: TestClient, world: World):
    headers = world.a.act(client, "other_patient")
    for label, method, url, body in _requests(world.a, world.seed_a):
        response = _send(client, method, url, body, headers)
        assert response.status_code in DENIED, f"{label} -> {response.status_code}"
        assert SECRET not in response.text, label
    assert client.get("/api/v1/appointments").json() == []
    assert client.get("/api/v1/notifications").json() == []
    _assert_untouched(client, world.a, world.seed_a)


def test_staff_never_see_or_consume_a_patients_notifications(client: TestClient, world: World):
    for role in ("doctor", "nurse", "admin", "clinic_admin"):
        headers = world.a.act(client, role)
        assert client.get("/api/v1/notifications").json() == []
        response = client.post(f"/api/v1/notifications/{world.seed_a.notification}/read", headers=headers)
        assert response.status_code == 404
    _assert_untouched(client, world.a, world.seed_a)


def test_patient_sees_only_their_own_records_in_each_list(client: TestClient, world: World):
    own = prescribe(client, world.a, "Own drug")
    other_patient_id = world.a.other_patient_id
    world.a.act(client, "doctor")
    other = client.post(
        f"/api/v1/patients/{other_patient_id}/medications",
        headers=use(client, world.a.who["doctor"]),
        json={"name": "Other drug", "dosage": "1 mg", "start_date": "2026-01-01"},
    ).json()
    world.a.act(client, "patient")
    names = {row["name"] for row in client.get(f"/api/v1/patients/{world.a.patient_id}/medications").json()}
    assert "Own drug" in names
    assert "Other drug" not in names
    assert client.get(f"/api/v1/medications/{other['id']}").status_code == 404
    assert client.get(f"/api/v1/medications/{own['id']}").status_code == 200
    world.a.act(client, "other_patient")
    assert client.get(f"/api/v1/medications/{own['id']}").status_code == 404


@pytest.mark.parametrize("bad_id", ["1", "0", "-1", "abc", "../etc/passwd"])
def test_sequential_or_malformed_ids_are_rejected(client: TestClient, world: World, bad_id: str):
    world.a.act(client, "doctor")
    for path in (
        f"/api/v1/appointments/{bad_id}",
        f"/api/v1/medical-records/{bad_id}",
        f"/api/v1/medications/{bad_id}",
        f"/api/v1/consents/{bad_id}",
        f"/api/v1/patients/{bad_id}/medical-records",
        f"/api/v1/patients/{bad_id}/medications",
        f"/api/v1/patients/{bad_id}/consents",
    ):
        assert client.get(path).status_code in {404, 422}, path


def test_guessed_uuids_resolve_to_not_found_for_every_role(client: TestClient, world: World):
    ghost = "00000000-0000-4000-8000-000000000001"
    for role in ALL_ROLES:
        world.a.act(client, role)
        for path in (
            f"/api/v1/appointments/{ghost}",
            f"/api/v1/medical-records/{ghost}",
            f"/api/v1/medications/{ghost}",
            f"/api/v1/consents/{ghost}",
        ):
            assert client.get(path).status_code in DENIED, (role, path)


# --- multi-tenancy --------------------------------------------------------


@pytest.mark.parametrize("attacker_is_b", [True, False], ids=["B-attacks-A", "A-attacks-B"])
@pytest.mark.parametrize("role", ALL_ROLES)
def test_a_clinic_can_never_reach_the_other_clinics_data(
    client: TestClient, world: World, attacker_is_b: bool, role: str
):
    attacker, victim, seed = (world.b, world.a, world.seed_a) if attacker_is_b else (world.a, world.b, world.seed_b)
    headers = attacker.act(client, role)
    for label, method, url, body in _requests(victim, seed):
        response = _send(client, method, url, body, headers)
        assert response.status_code in DENIED, f"{role}: {label} -> {response.status_code}"
        assert SECRET not in response.text, f"{role}: {label} leaked"
    _assert_untouched(client, victim, seed)


def test_each_clinic_lists_only_its_own_data(client: TestClient, world: World):
    for tenant, seed, other in ((world.a, world.seed_a, world.seed_b), (world.b, world.seed_b, world.seed_a)):
        for role in ("doctor", "nurse", "admin", "clinic_admin", "patient"):
            tenant.act(client, role)
            appointments = client.get("/api/v1/appointments").json()
            assert [row["id"] for row in appointments] == [seed.appointment]
            assert {row["clinic_id"] for row in appointments} == {tenant.clinic_id}
            assert other.appointment not in client.get("/api/v1/appointments").text

        tenant.act(client, "doctor")
        for path, key in (("medical-records", seed.record), ("medications", seed.medication)):
            rows = client.get(f"/api/v1/patients/{tenant.patient_id}/{path}").json()
            assert [row["id"] for row in rows] == [key]
            assert {row["clinic_id"] for row in rows} == {tenant.clinic_id}
        tenant.act(client, "patient")
        consents = client.get(f"/api/v1/patients/{tenant.patient_id}/consents").json()
        assert [row["id"] for row in consents] == [seed.consent]
        notifications = client.get("/api/v1/notifications").json()
        assert [row["id"] for row in notifications] == [seed.notification]


def test_foreign_ids_inside_request_bodies_cannot_cross_tenants(client: TestClient, world: World):
    a, b = world.a, world.b
    own = book(client, b, scheduled_at=slot(days=9))
    for role in ("doctor", "clinic_admin"):
        headers = b.act(client, role)
        for patient_id, staff_id in (
            (a.patient_id, b.staff_ids["doctor"]),
            (b.patient_id, a.staff_ids["doctor"]),
            (a.patient_id, a.staff_ids["doctor"]),
        ):
            response = client.post(
                "/api/v1/appointments",
                headers=headers,
                json={"patient_id": patient_id, "staff_id": staff_id, "scheduled_at": slot(days=11)},
            )
            assert response.status_code == 404, (role, patient_id, staff_id)
        for body in ({"patient_id": a.patient_id}, {"staff_id": a.staff_ids["doctor"]}):
            moved = client.patch(f"/api/v1/appointments/{own['id']}", headers=headers, json=body)
            assert moved.status_code == 404, body

    headers = b.act(client, "doctor")
    assert client.get(f"/api/v1/appointments/{own['id']}").json() == own
    assert (
        client.post(
            f"/api/v1/patients/{a.patient_id}/medical-records",
            headers=headers,
            json={"title": "x", "content": "y"},
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/patients/{a.patient_id}/medications",
            headers=headers,
            json={"name": "x", "dosage": "1", "start_date": "2026-01-01"},
        ).status_code
        == 404
    )
    headers = b.act(client, "patient")
    assert (
        client.post(
            f"/api/v1/patients/{a.patient_id}/consents",
            headers=headers,
            json={"consent_type": "treatment", "purpose": "cross"},
        ).status_code
        == 404
    )
    _assert_untouched(client, a, world.seed_a)
    assert len(_db_rows(client, Appointment)) == 3  # A's, B's seed and B's own


@pytest.mark.parametrize(
    ("path_template", "body"),
    [
        ("/api/v1/appointments/{appointment}", {"clinic_id": "{other_clinic}"}),
        ("/api/v1/medical-records/{record}", {"title": "x", "content": "y", "clinic_id": "{other_clinic}"}),
        ("/api/v1/medical-records/{record}", {"title": "x", "content": "y", "patient_id": "{other_patient}"}),
        ("/api/v1/medical-records/{record}", {"title": "x", "content": "y", "author_staff_id": "{other_staff}"}),
        ("/api/v1/medications/{medication}", {"clinic_id": "{other_clinic}"}),
        ("/api/v1/medications/{medication}", {"patient_id": "{other_patient}"}),
        ("/api/v1/medications/{medication}", {"prescribed_by_staff_id": "{other_staff}"}),
    ],
)
def test_updates_cannot_rewrite_tenant_or_patient_ownership(
    client: TestClient, world: World, path_template: str, body: dict
):
    seed = world.seed_a
    values = {
        "{other_clinic}": world.b.clinic_id,
        "{other_patient}": world.b.patient_id,
        "{other_staff}": world.b.staff_ids["doctor"],
    }
    body = {key: values.get(value, value) for key, value in body.items()}
    url = path_template.format(
        appointment=seed.appointment, record=seed.record, medication=seed.medication
    )
    headers = world.a.act(client, "doctor")
    assert client.patch(url, headers=headers, json=body).status_code == 422

    owner = {
        Appointment: seed.appointment,
        MedicalRecord: seed.record,
        Medication: seed.medication,
    }
    for model, row_id in owner.items():
        (row,) = [row for row in _db_rows(client, model) if str(row.id) == row_id]
        assert str(row.clinic_id) == world.a.clinic_id
        assert str(row.patient_id) == world.a.patient_id
    _assert_untouched(client, world.a, seed)


def test_notification_scoping_ignores_rows_whose_clinic_does_not_match_the_user(
    client: TestClient, world: World
):
    with client.session_factory() as db:  # type: ignore[attr-defined]
        stray = Notification(
            clinic_id=world.b.clinic_id,
            user_id=world.a.user_ids["patient"],
            title=f"{SECRET}-STRAY",
            message="mismatched tenant",
        )
        db.add(stray)
        db.commit()
        stray_id = str(stray.id)

    headers = world.a.act(client, "patient")
    listed = client.get("/api/v1/notifications")
    assert stray_id not in listed.text
    assert listed.headers["x-total-count"] == "1"
    assert client.post(f"/api/v1/notifications/{stray_id}/read", headers=headers).status_code == 404


# --- audit trail ----------------------------------------------------------


def test_audit_trail_is_not_exposed_and_does_not_leak_across_tenants(client: TestClient, world: World):
    paths = app.openapi()["paths"]
    assert not [path for path in paths if "audit" in path.lower()]

    for role in ("doctor", "patient", "clinic_admin"):
        world.b.act(client, role)
        for _label, method, url, body in _requests(world.a, world.seed_a):
            _send(client, method, url, body, {settings.CSRF_HEADER_NAME: world.b.who[role]["csrf"]})

    users_a = set(world.a.user_ids.values())
    users_b = set(world.b.user_ids.values())
    rows = _db_rows(client, AuditLog)
    assert rows
    for row in rows:
        actor = str(row.actor_user_id) if row.actor_user_id else None
        clinic = str(row.clinic_id) if row.clinic_id else None
        if actor in users_b:
            assert clinic in {world.b.clinic_id, None}, row.action
        if actor in users_a:
            assert clinic in {world.a.clinic_id, None}, row.action
        blob = f"{row.event_metadata} {row.resource_type} {row.actor_email} {row.user_agent}"
        assert SECRET not in blob
        assert "INJECTED" not in blob

    # B's probing is recorded in B's trail only; A's trail contains nothing done by B.
    assert not [row for row in rows if str(row.clinic_id) == world.a.clinic_id and str(row.actor_user_id) in users_b]
    assert [row for row in rows if str(row.actor_user_id) in users_b and row.action.value == "permission_denied"]
