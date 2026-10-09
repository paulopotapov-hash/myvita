"""
P2.1 — public clinic directory hardening.

Policy under test: a clinic is visible in GET /api/v1/clinics[/{id}] only if
(public patient registration is on AND the clinic is in PUBLIC_CLINIC_IDS) OR
it is the caller's own clinic. List and detail share one predicate; the response
is the explicit {id, name} schema; private and nonexistent clinics are
indistinguishable (404).
"""

from __future__ import annotations

import uuid

import pytest

from app.core.config import settings
from tests.phase1_world import Actor, World

LIST = "/api/v1/clinics"
APPROVED_FIELDS = {"id", "name"}
INTERNAL_MARKERS = (
    "nif",
    "address",
    "phone",
    "created_at",
    "updated_at",
    "patients",
    "staff",
    "users",
    "email",
)


@pytest.fixture()
def public_registration(monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_PUBLIC_PATIENT_REGISTRATION", True)
    monkeypatch.setattr(settings, "PUBLIC_CLINIC_IDS", [])


def _allow(monkeypatch, *clinic_ids: str) -> None:
    monkeypatch.setattr(settings, "PUBLIC_CLINIC_IDS", [uuid.UUID(c) for c in clinic_ids])


def _extra_clinic(index: int, name: str) -> str:
    admin = Actor(f"p21-extra-{index}", f"p21-admin-{index}-{uuid.uuid4().hex[:6]}@phase1.example")
    response = admin.post(
        LIST,
        json={
            "clinic_name": name,
            "admin_full_name": f"Admin {index}",
            "admin_email": admin.email,
            "admin_password": "Phase1-Synthetic-Pass-9!",
        },
        csrf=False,
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


# --------------------------------------------------------------------------
# List visibility
# --------------------------------------------------------------------------


def test_public_clinic_appears_only_when_allowlisted_and_registration_is_open(world: World, monkeypatch):
    anon = Actor("anon")
    monkeypatch.setattr(settings, "PUBLIC_CLINIC_IDS", [])
    monkeypatch.setattr(settings, "ALLOW_PUBLIC_PATIENT_REGISTRATION", True)
    assert anon.get(LIST).json() == []  # open registration alone exposes nothing

    _allow(monkeypatch, world.a.clinic_id)
    body = anon.get(LIST).json()
    assert [c["id"] for c in body] == [world.a.clinic_id]  # intended-public clinic only; B stays private

    monkeypatch.setattr(settings, "ALLOW_PUBLIC_PATIENT_REGISTRATION", False)
    assert anon.get(LIST).json() == []  # the existing global switch still closes everything


def test_private_clinic_never_appears_publicly(world: World, public_registration, monkeypatch):
    _allow(monkeypatch, world.a.clinic_id)
    anon_ids = {c["id"] for c in Actor("anon").get(LIST).json()}
    assert world.b.clinic_id not in anon_ids


def test_signed_in_users_see_their_own_clinic_plus_public_ones_never_other_private_clinics(
    world: World, public_registration, monkeypatch
):
    _allow(monkeypatch, world.b.clinic_id)  # only B is public
    for actor in (world.a.doctor, world.a.admin, world.a.patients["a1"]):
        assert {c["id"] for c in actor.get(LIST).json()} == {world.a.clinic_id, world.b.clinic_id}
    # B's users see B only (A is private); the public flag does not make A visible to anyone.
    assert {c["id"] for c in world.b.admin.get(LIST).json()} == {world.b.clinic_id}
    monkeypatch.setattr(settings, "ALLOW_PUBLIC_PATIENT_REGISTRATION", False)
    assert {c["id"] for c in world.a.doctor.get(LIST).json()} == {world.a.clinic_id}


def test_list_response_contains_only_approved_public_fields(world: World, public_registration, monkeypatch):
    _allow(monkeypatch, world.a.clinic_id)
    response = Actor("anon").get(LIST)
    assert response.status_code == 200
    items = response.json()
    assert items and all(set(item) == APPROVED_FIELDS for item in items)
    own = world.a.admin.get(LIST).json()
    assert all(set(item) == APPROVED_FIELDS for item in own)
    lowered = (response.text + str(own)).lower()
    for marker in INTERNAL_MARKERS:
        assert f'"{marker}"' not in lowered
    for leaked in (
        world.a.admin.email,
        world.a.doctor.email,
        world.a.doctor.user_id,
        world.a.doctor.staff_id,
        world.a.patients["a1"].patient_id,
        world.a.patients["a1"].email,
    ):
        assert leaked and leaked not in response.text
    assert "set-cookie" not in {k.lower() for k in response.headers}


# --------------------------------------------------------------------------
# Pagination
# --------------------------------------------------------------------------


def test_pagination_bounds_total_count_and_cannot_be_used_to_enumerate(
    world: World, public_registration, monkeypatch
):
    extras = [_extra_clinic(i, f"P21 Pagination {i:02d}") for i in range(5)]
    _allow(monkeypatch, world.a.clinic_id, *extras)  # world.b is deliberately private
    anon = Actor("anon")

    page1 = anon.get(f"{LIST}?page=1&page_size=2")
    page2 = anon.get(f"{LIST}?page=2&page_size=2")
    page3 = anon.get(f"{LIST}?page=3&page_size=2")
    assert page1.headers["X-Total-Count"] == "6" and len(page1.json()) == 2
    assert len(page2.json()) == 2 and len(page3.json()) == 2
    ids = [c["id"] for p in (page1, page2, page3) for c in p.json()]
    assert len(set(ids)) == 6 and set(ids) == {world.a.clinic_id, *extras}
    assert world.b.clinic_id not in ids
    assert anon.get(f"{LIST}?page=4&page_size=2").json() == []  # past the end is empty, not an error leak
    names = [c["name"] for p in (page1, page2, page3) for c in p.json()]
    assert names == sorted(names)  # deterministic order

    for bad in (
        "page=0",
        "page=-1",
        "page_size=0",
        "page_size=101",
        "page_size=100000",
        "page=abc",
        "page_size=x",
    ):
        assert anon.get(f"{LIST}?{bad}").status_code == 422, bad
    assert anon.get(f"{LIST}?page_size=100").status_code == 200


def test_total_count_header_does_not_count_private_clinics(world: World, public_registration, monkeypatch):
    _allow(monkeypatch, world.a.clinic_id)
    anon_total = Actor("anon").get(LIST).headers["X-Total-Count"]
    assert anon_total == "1"
    monkeypatch.setattr(settings, "PUBLIC_CLINIC_IDS", [])
    assert Actor("anon").get(LIST).headers["X-Total-Count"] == "0"


# --------------------------------------------------------------------------
# Detail + IDOR
# --------------------------------------------------------------------------


def test_public_clinic_detail_works_with_exactly_the_approved_fields(
    world: World, public_registration, monkeypatch
):
    _allow(monkeypatch, world.a.clinic_id)
    response = Actor("anon").get(f"{LIST}/{world.a.clinic_id}")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == APPROVED_FIELDS and body["id"] == world.a.clinic_id
    assert body["name"] == "Phase1 Clinic A"


def test_private_and_nonexistent_clinics_are_indistinguishable(
    world: World, public_registration, monkeypatch
):
    _allow(monkeypatch, world.a.clinic_id)
    anon = Actor("anon")
    private = anon.get(f"{LIST}/{world.b.clinic_id}")
    missing = anon.get(f"{LIST}/{uuid.uuid4()}")
    assert private.status_code == missing.status_code == 404
    assert private.json() == missing.json()
    assert world.b.clinic_id not in private.text and "Phase1 Clinic B" not in private.text
    assert anon.get(f"{LIST}/not-a-uuid").status_code == 422


def test_detail_follows_the_same_policy_as_the_list_for_every_actor_and_flag_state(
    world: World, public_registration, monkeypatch
):
    actors = {
        "anon": Actor("anon"),
        "a_admin": world.a.admin,
        "a_doctor": world.a.doctor,
        "a_patient": world.a.patients["a1"],
        "b_patient": world.b.patients["b1"],
    }
    for public_ids in ([], [world.a.clinic_id], [world.b.clinic_id], [world.a.clinic_id, world.b.clinic_id]):
        for registration in (True, False):
            monkeypatch.setattr(settings, "ALLOW_PUBLIC_PATIENT_REGISTRATION", registration)
            _allow(monkeypatch, *public_ids)
            for label, actor in actors.items():
                listed = {c["id"] for c in actor.get(LIST).json()}
                for clinic_id in (world.a.clinic_id, world.b.clinic_id):
                    status = actor.get(f"{LIST}/{clinic_id}").status_code
                    assert (status == 200) == (clinic_id in listed), (
                        label,
                        public_ids,
                        registration,
                        clinic_id,
                    )


def test_idor_a_user_cannot_read_another_private_clinic_by_id(world: World, public_registration):
    for actor, other in (
        (world.a.doctor, world.b),
        (world.a.patients["a1"], world.b),
        (world.b.admin, world.a),
    ):
        response = actor.get(f"{LIST}/{other.clinic_id}")
        assert response.status_code == 404 and other.clinic_id not in response.text


def test_detail_never_exposes_people_or_clinical_data(world: World, public_registration, monkeypatch):
    _allow(monkeypatch, world.a.clinic_id)
    text = Actor("anon").get(f"{LIST}/{world.a.clinic_id}").text
    patient = world.a.patients["a1"]
    for secret in (
        patient.patient_id,
        patient.user_id,
        patient.email,
        world.a.doctor.staff_id,
        world.a.doctor.email,
        world.a.admin.email,
        patient.res["record"],
        patient.res["appointment"],
    ):
        assert secret not in text


# --------------------------------------------------------------------------
# Does not weaken anything else
# --------------------------------------------------------------------------


def test_public_directory_is_read_only_and_creates_no_session(world: World, public_registration, monkeypatch):
    _allow(monkeypatch, world.a.clinic_id)
    anon = Actor("anon")
    for method in ("POST", "PATCH", "PUT", "DELETE"):
        assert anon.call(method, f"{LIST}/{world.a.clinic_id}", json={}, csrf=False).status_code in {
            401,
            403,
            405,
        }
    assert anon.session_token is None


def test_authenticated_clinical_routes_still_reject_anonymous_callers_when_the_directory_is_public(
    world: World, public_registration, monkeypatch
):
    _allow(monkeypatch, world.a.clinic_id)
    anon = Actor("anon")
    for path in (
        "/api/v1/patients",
        "/api/v1/staff",
        "/api/v1/appointments",
        "/api/v1/auth/me",
    ):
        assert anon.get(path).status_code == 401, path


def test_allowlist_setting_fails_closed_on_bad_input():
    from pydantic import ValidationError

    from app.core.config import Settings

    assert Settings(JWT_SECRET_KEY="x" * 40).PUBLIC_CLINIC_IDS == []
    with pytest.raises(ValidationError):
        Settings(JWT_SECRET_KEY="x" * 40, PUBLIC_CLINIC_IDS=["not-a-uuid"])
