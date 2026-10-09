"""
P2.2 — patient onboarding through invitations, end to end on the committed
two-clinic dataset (tests/phase1_world.py): creation, acceptance, login,
isolation, revocation, listing, abuse cases and concurrent acceptance.
"""
from __future__ import annotations

import logging
import threading
import uuid

from sqlalchemy import select

from app.core.rate_limit import limiter
from app.models import AuditAction, AuditLog, AuditResult, Invitation, InvitationStatus, Patient, User
from tests.phase1_world import PASSWORD, Actor, World

NEW_PASSWORD = "PacienteNovo123!"


def _email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@onboarding.example"


def _invite(actor: Actor, email: str, full_name: str = "Paciente Convidado"):
    return actor.post("/api/v1/invitations/patients", json={"email": email, "full_name": full_name})


def _accept(token: str, password: str = NEW_PASSWORD, **extra) -> tuple[Actor, object]:
    limiter.reset()
    newcomer = Actor("newcomer")
    response = newcomer.post("/api/v1/invitations/accept", json={"token": token, "password": password, **extra})
    return newcomer, response


def test_patient_onboarding_happy_path_binds_the_server_side_clinic(world: World):
    email = _email("happy")
    created = _invite(world.a.doctor, email, "Ana Convidada")
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["role"] == "patient"
    assert body["clinic_id"] == world.a.clinic_id
    assert body["status"] == "pending"
    token = body["token"]

    limiter.reset()
    anonymous = Actor("anon")
    preview = anonymous.post("/api/v1/invitations/preview", json={"token": token})
    assert preview.status_code == 200
    assert preview.json()["email"] == email and preview.json()["role"] == "patient"

    patient, accepted = _accept(token)
    assert accepted.status_code == 200, accepted.text
    me = patient.load_identity()
    assert me["role"] == "patient"
    assert me["clinic_id"] == world.a.clinic_id
    assert me["patient_id"]

    with world.db() as db:
        user = db.scalars(select(User).where(User.email == email)).one()
        profile = db.scalars(select(Patient).where(Patient.user_id == user.id)).one()
        invitation = db.get(Invitation, uuid.UUID(body["id"]))
        assert str(user.clinic_id) == world.a.clinic_id == str(profile.clinic_id)
        assert user.full_name == "Ana Convidada"
        assert invitation.status == InvitationStatus.ACCEPTED and invitation.accepted_at is not None

    # The new patient reads their own record, and nothing else.
    assert patient.get(f"/api/v1/patients/{me['patient_id']}").status_code == 200
    other_same_clinic = world.a.patients["a1"].patient_id
    other_clinic = world.b.patients["b1"].patient_id
    for patient_id in (other_same_clinic, other_clinic):
        assert patient.get(f"/api/v1/patients/{patient_id}").status_code == 404
        assert patient.get(f"/api/v1/patients/{patient_id}/medical-records").status_code == 404
    assert patient.get("/api/v1/patients").status_code == 403
    assert patient.get("/api/v1/invitations").status_code == 403

    # Normal login works afterwards; the invitation cannot be used again.
    relogin = Actor("relogin", email)
    assert relogin.login(NEW_PASSWORD).status_code == 200
    assert relogin.load_identity()["patient_id"] == me["patient_id"]
    _, reused = _accept(token, "OutraSenhaForte123!")
    assert reused.status_code == 410


def test_acceptance_cannot_choose_clinic_patient_or_role(world: World):
    email = _email("smuggle")
    token = _invite(world.a.nurse, email).json()["token"]
    for field, value in (
        ("clinic_id", world.b.clinic_id),
        ("patient_id", world.a.patients["a1"].patient_id),
        ("role", "clinic_admin"),
        ("email", "someone-else@onboarding.example"),
    ):
        _, response = _accept(token, **{field: value})
        assert response.status_code == 422, field
    with world.db() as db:
        assert db.scalars(select(User).where(User.email == email)).first() is None
    # Creation cannot target another clinic or patient either.
    smuggled = world.a.doctor.post(
        "/api/v1/invitations/patients",
        json={"email": _email("x"), "full_name": "X Y", "clinic_id": world.b.clinic_id},
    )
    assert smuggled.status_code == 422


def test_only_clinical_staff_and_admins_create_patient_invitations(world: World):
    limiter.reset()
    for actor in (world.a.doctor, world.a.nurse, world.a.admin):
        assert _invite(actor, _email(actor.key)).status_code == 201
    assert _invite(world.a.staff_admin, _email("office")).status_code == 403
    assert _invite(world.a.patients["a1"], _email("patient")).status_code == 403
    assert Actor("anon").post(
        "/api/v1/invitations/patients", json={"email": _email("anon"), "full_name": "Anon Y"}
    ).status_code == 401
    # An email that already has an account (in any clinic) cannot be invited.
    assert _invite(world.a.doctor, world.b.patients["b1"].email).status_code == 409


def test_revoked_and_superseded_invitations_cannot_be_used(world: World):
    limiter.reset()
    email = _email("revoke")
    first = _invite(world.a.doctor, email).json()
    revoked = world.a.doctor.post(f"/api/v1/invitations/{first['id']}/revoke")
    assert revoked.status_code == 200 and revoked.json()["status"] == "revoked"
    assert "token" not in revoked.json()
    _, response = _accept(first["token"])
    assert response.status_code == 410
    assert Actor("anon").post("/api/v1/invitations/preview", json={"token": first["token"]}).status_code == 410
    assert world.a.doctor.post(f"/api/v1/invitations/{first['id']}/revoke").status_code == 409

    # Re-inviting the same email supersedes the older pending invitation.
    older = _invite(world.a.doctor, email).json()
    newer = _invite(world.a.nurse, email).json()
    _, response = _accept(older["token"])
    assert response.status_code == 410
    _, response = _accept(newer["token"])
    assert response.status_code == 200
    assert world.a.doctor.post(f"/api/v1/invitations/{newer['id']}/revoke").status_code == 409


def test_revoke_and_list_are_tenant_and_role_scoped(world: World):
    limiter.reset()
    patient_invite = _invite(world.a.doctor, _email("scoped")).json()
    staff_invite = world.a.admin.post(
        "/api/v1/invitations/staff",
        json={"email": _email("staff"), "full_name": "Staff Convidado", "staff_role": "nurse"},
    ).json()

    # Another clinic, a patient, admin-role staff or anonymous callers cannot revoke (IDOR -> 404/403/401).
    for actor in (world.b.admin, world.b.doctor):
        assert actor.post(f"/api/v1/invitations/{patient_invite['id']}/revoke").status_code == 404
    assert world.a.patients["a1"].post(f"/api/v1/invitations/{patient_invite['id']}/revoke").status_code == 403
    assert world.a.staff_admin.post(f"/api/v1/invitations/{patient_invite['id']}/revoke").status_code == 403
    assert Actor("anon").post(f"/api/v1/invitations/{patient_invite['id']}/revoke").status_code == 401
    # Clinical staff manage patient invitations only.
    assert world.a.doctor.post(f"/api/v1/invitations/{staff_invite['id']}/revoke").status_code == 404
    assert world.a.doctor.post(f"/api/v1/invitations/{uuid.uuid4()}/revoke").status_code == 404

    doctor_view = world.a.doctor.get("/api/v1/invitations?page_size=100")
    assert doctor_view.status_code == 200
    ids = {item["id"] for item in doctor_view.json()}
    assert patient_invite["id"] in ids and staff_invite["id"] not in ids
    assert all(item["role"] == "patient" and item["clinic_id"] == world.a.clinic_id for item in doctor_view.json())
    assert all("token" not in item and "token_hash" not in item for item in doctor_view.json())
    admin_ids = {item["id"] for item in world.a.admin.get("/api/v1/invitations?page_size=100").json()}
    assert {patient_invite["id"], staff_invite["id"]} <= admin_ids
    assert patient_invite["id"] not in {item["id"] for item in world.b.admin.get("/api/v1/invitations?page_size=100").json()}
    assert world.a.staff_admin.get("/api/v1/invitations").status_code == 403
    assert Actor("anon").get("/api/v1/invitations").status_code == 401

    assert world.a.admin.post(f"/api/v1/invitations/{staff_invite['id']}/revoke").status_code == 200
    assert world.a.nurse.post(f"/api/v1/invitations/{patient_invite['id']}/revoke").status_code == 200
    assert patient_invite["id"] not in {item["id"] for item in world.a.doctor.get("/api/v1/invitations").json()}


def test_invalid_tokens_fail_uniformly_without_leaking(world: World):
    for token in ("x" * 39, "x" * 201, "not-a-real-invitation-token-value-000000000000", "🙂" * 40):
        _, response = _accept(token)
        assert response.status_code in {404, 422}
        assert "@" not in response.text and world.a.clinic_id not in response.text
        preview = Actor("anon").post("/api/v1/invitations/preview", json={"token": token})
        assert preview.status_code in {404, 422}
        assert "@" not in preview.text


def test_concurrent_acceptance_creates_exactly_one_account(world: World):
    email = _email("race")
    token = _invite(world.a.doctor, email).json()["token"]
    limiter.reset()
    clients = [Actor(f"racer-{i}") for i in range(4)]
    barrier = threading.Barrier(len(clients))
    statuses: list[int] = []

    def accept(actor: Actor) -> None:
        barrier.wait()
        response = actor.post("/api/v1/invitations/accept", json={"token": token, "password": NEW_PASSWORD})
        statuses.append(response.status_code)

    threads = [threading.Thread(target=accept, args=(actor,)) for actor in clients]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(statuses).count(200) == 1, statuses
    assert all(code in {200, 409, 410} for code in statuses), statuses
    with world.db() as db:
        users = db.scalars(select(User).where(User.email == email)).all()
        assert len(users) == 1
        assert db.scalars(select(Patient).where(Patient.user_id == users[0].id)).one()


def test_invitation_lifecycle_is_audited_without_tokens(world: World, caplog):
    limiter.reset()
    caplog.set_level(logging.DEBUG)
    created = _invite(world.a.doctor, _email("audit")).json()
    revoked_invite = _invite(world.a.doctor, _email("audit-revoked")).json()
    assert world.a.doctor.post(f"/api/v1/invitations/{revoked_invite['id']}/revoke").status_code == 200
    _, accepted = _accept(created["token"])
    assert accepted.status_code == 200
    _, rejected = _accept(created["token"])
    assert rejected.status_code == 410
    _, unknown = _accept("not-a-real-invitation-token-value-111111111111")
    assert unknown.status_code == 404

    with world.db() as db:
        def events(action, resource_id=None, result=AuditResult.SUCCESS):
            query = select(AuditLog).where(AuditLog.action == action, AuditLog.result == result)
            if resource_id:
                query = query.where(AuditLog.resource_id == uuid.UUID(resource_id))
            return db.scalars(query).all()

        assert events(AuditAction.INVITATION_CREATED, created["id"])
        revoked = events(AuditAction.INVITATION_REVOKED, revoked_invite["id"])
        assert len(revoked) == 1 and str(revoked[0].clinic_id) == world.a.clinic_id
        assert events(AuditAction.INVITATION_ACCEPTED, created["id"])
        failures = events(AuditAction.INVITATION_ACCEPTED, result=AuditResult.FAILURE)
        reasons = {row.event_metadata.get("reason") for row in failures if row.event_metadata}
        assert {"not_pending", "invalid_token"} <= reasons
        for row in db.scalars(select(AuditLog)).all():
            serialized = repr(row.event_metadata) + str(row.resource_type)
            assert created["token"] not in serialized and revoked_invite["token"] not in serialized

    for token in (created["token"], revoked_invite["token"]):
        assert token not in caplog.text


def test_password_policy_and_existing_account_on_acceptance(world: World):
    token = _invite(world.a.doctor, _email("weak")).json()["token"]
    _, weak = _accept(token, "password")
    assert weak.status_code == 422
    # An invitation whose email gains an account elsewhere before acceptance is refused safely.
    email = _email("taken")
    token = _invite(world.a.doctor, email).json()["token"]
    limiter.reset()
    registered = Actor("other", email).post(
        "/api/v1/patients/register",
        json={"clinic_id": world.b.clinic_id, "full_name": "Other Clinic", "email": email, "password": PASSWORD},
        csrf=False,
    )
    assert registered.status_code == 201, registered.text  # tests enable public registration (conftest)
    _, response = _accept(token)
    assert response.status_code == 409
    with world.db() as db:
        users = db.scalars(select(User).where(User.email == email)).all()
        assert len(users) == 1 and str(users[0].clinic_id) == world.b.clinic_id
