"""
Account lifecycle: admin-issued password resets, the anonymous reset request,
forced password change, deactivation/reactivation, admin MFA reset, tenant
isolation, case-insensitive e-mail identity and operator recovery of clinic
admins.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

from app import account_recovery
from app.core.security import ACCOUNT_ACTION_HEADER, hash_password
from app.models import PasswordResetToken, Patient, User, UserMfa, UserRole
from app.modules.users import service as users_service
from tests.account_support import (
    NEW_PASSWORD,
    PASSWORD,
    audit_rows,
    create_staff,
    enrol_mfa,
    login,
    onboard_clinic,
    post,
    register_patient,
    user_id_by_email,
)

ADMIN = "admin@clinica.pt"
STAFF = "enfermeiro@clinica.pt"
PATIENT = "paciente@example.com"


def _setup(client) -> dict:
    clinic = onboard_clinic(client, ADMIN)
    create_staff(client, STAFF, staff_role="nurse")
    register_patient(client, clinic["id"], PATIENT)
    login(client, ADMIN)
    return clinic


def _issue_reset(client, email: str):
    return post(client, f"/api/v1/users/{user_id_by_email(client, email)}/password-reset")


def _confirm(client, token: str, password: str = NEW_PASSWORD):
    client.cookies.clear()
    return client.post("/api/v1/auth/password-reset/confirm", json={"token": token, "new_password": password})


# --- admin-issued password reset ----------------------------------------------------


def test_reset_link_works_exactly_once_and_revokes_sessions(client, second_client):
    _setup(client)
    login(second_client, STAFF)
    issued = _issue_reset(client, STAFF)
    assert issued.status_code == 201
    token = issued.json()["token"]
    assert len(token) >= 60

    audit = audit_rows(client, "password_reset_issued")
    assert len(audit) == 1 and token not in str(audit[0].event_metadata)
    assert audit[0].actor_email == ADMIN

    assert _confirm(client, token).status_code == 204
    assert _confirm(client, token, "MaisUmaSenha789!").status_code == 400
    assert second_client.get("/api/v1/auth/me").status_code == 401
    assert login(client, STAFF).status_code == 401
    assert login(client, STAFF, NEW_PASSWORD).status_code == 200
    assert len(audit_rows(client, "password_reset_completed")) == 1


def test_only_the_hash_of_a_reset_token_is_stored(client):
    _setup(client)
    token = _issue_reset(client, STAFF).json()["token"]
    with client.session_factory() as db:
        stored = db.query(PasswordResetToken).one()
        assert stored.token_hash != token and len(stored.token_hash) == 64


def test_expired_reset_link_is_rejected(client):
    _setup(client)
    token = _issue_reset(client, STAFF).json()["token"]
    with client.session_factory() as db:
        db.query(PasswordResetToken).update({PasswordResetToken.expires_at: datetime.now(UTC) - timedelta(seconds=1)})
        db.commit()
    assert _confirm(client, token).status_code == 400


def test_issuing_a_new_link_revokes_the_previous_one(client):
    _setup(client)
    first = _issue_reset(client, STAFF).json()["token"]
    second = _issue_reset(client, STAFF).json()["token"]
    assert _confirm(client, first).status_code == 400
    assert _confirm(client, second).status_code == 204


def test_weak_or_unknown_reset_input_is_rejected(client):
    _setup(client)
    token = _issue_reset(client, STAFF).json()["token"]
    assert _confirm(client, token, "password").status_code == 422
    assert _confirm(client, "x" * 64).status_code == 400


def test_reset_clears_forced_change_but_never_bypasses_mfa(client, totp_clock):
    _setup(client)
    login(client, STAFF)
    enrol_mfa(client, totp_clock)
    login(client, ADMIN)
    post(client, f"/api/v1/users/{user_id_by_email(client, STAFF)}/require-password-change")
    token = _issue_reset(client, STAFF).json()["token"]
    assert _confirm(client, token).status_code == 204
    with client.session_factory() as db:
        assert db.get(User, uuid.UUID(user_id_by_email(client, STAFF))).must_change_password is False
    assert login(client, STAFF, NEW_PASSWORD).status_code == 202


def test_deactivation_revokes_outstanding_reset_links(client):
    _setup(client)
    staff_id = user_id_by_email(client, STAFF)
    token = _issue_reset(client, STAFF).json()["token"]
    post(client, f"/api/v1/users/{staff_id}/deactivate")
    post(client, f"/api/v1/users/{staff_id}/reactivate")
    assert _confirm(client, token).status_code == 400


def test_reset_is_refused_for_inactive_self_and_other_admins(client):
    _setup(client)
    staff_id = user_id_by_email(client, STAFF)
    post(client, f"/api/v1/users/{staff_id}/deactivate")
    assert _issue_reset(client, STAFF).status_code == 409
    assert _issue_reset(client, ADMIN).status_code == 409

    other_admin = _second_admin(client)
    assert post(client, f"/api/v1/users/{other_admin}/password-reset").status_code == 403
    assert post(client, f"/api/v1/users/{other_admin}/require-password-change").status_code == 403
    assert post(client, f"/api/v1/users/{other_admin}/mfa/reset").status_code == 403


def test_anonymous_reset_request_never_issues_a_token_or_reveals_accounts(client):
    _setup(client)
    client.cookies.clear()
    known = client.post("/api/v1/auth/password-reset/request", json={"email": STAFF.upper()})
    unknown = client.post("/api/v1/auth/password-reset/request", json={"email": "ninguem@example.com"})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    with client.session_factory() as db:
        assert db.query(PasswordResetToken).count() == 0

    rows = audit_rows(client, "password_reset_requested")
    assert len(rows) == 2
    assert all(row.actor_user_id is None and row.actor_email is None for row in rows)
    found = next(row for row in rows if row.event_metadata["account_found"])
    assert str(found.resource_id) == user_id_by_email(client, STAFF)
    assert found.clinic_id is not None
    missing = next(row for row in rows if not row.event_metadata["account_found"])
    assert missing.resource_id is None and missing.clinic_id is None
    assert "ninguem@example.com" not in str(missing.event_metadata)
    assert missing.event_metadata["email_masked"] == "n***@example.com"


# --- forced password change / pending actions -------------------------------------------


def test_forced_password_change_blocks_everything_else(client):
    onboard_clinic(client, ADMIN)
    create_staff(client, STAFF, require_password_change=True)
    response = login(client, STAFF)
    assert response.status_code == 200
    assert response.json()["pending_action"] == "password_change"
    assert response.json()["must_change_password"] is True

    blocked = client.get("/api/v1/patients")
    assert blocked.status_code == 403
    assert blocked.headers[ACCOUNT_ACTION_HEADER] == "password_change"
    assert client.get("/api/v1/auth/me").status_code == 200

    changed = post(client, "/api/v1/auth/change-password", {"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    assert changed.status_code == 204
    assert client.get("/api/v1/patients").status_code == 200
    assert audit_rows(client, "password_change")[-1].event_metadata == {"forced": True}


def test_password_change_comes_before_mfa_enrolment(client, enforce_mfa, totp_clock):
    onboard_clinic(client, ADMIN)
    create_staff(client, STAFF, require_password_change=True)
    enforce_mfa()
    assert login(client, STAFF).json()["pending_action"] == "password_change"
    post(client, "/api/v1/auth/change-password", {"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    assert client.get("/api/v1/auth/me").json()["pending_action"] == "mfa_setup"
    enrol_mfa(client, totp_clock)
    assert client.get("/api/v1/auth/me").json()["pending_action"] is None


def test_logout_is_always_possible_with_a_pending_action(client):
    onboard_clinic(client, ADMIN)
    create_staff(client, STAFF, require_password_change=True)
    login(client, STAFF)
    assert post(client, "/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_admin_can_require_a_password_change(client, second_client):
    _setup(client)
    login(second_client, STAFF)
    response = post(client, f"/api/v1/users/{user_id_by_email(client, STAFF)}/require-password-change")
    assert response.status_code == 200 and response.json()["must_change_password"] is True
    blocked = second_client.get("/api/v1/patients")
    assert blocked.status_code == 403 and blocked.headers[ACCOUNT_ACTION_HEADER] == "password_change"
    assert len(audit_rows(client, "password_change_required")) == 1


def test_directly_created_staff_must_change_the_admin_chosen_password_by_default(client):
    onboard_clinic(client, ADMIN)
    response = post(
        client,
        "/api/v1/staff",
        {"full_name": "Sem Opção", "email": STAFF, "password": PASSWORD, "staff_role": "doctor"},
    )
    assert response.status_code == 201
    assert login(client, STAFF).json()["pending_action"] == "password_change"


# --- deactivation / reactivation --------------------------------------------------------


def test_deactivate_and_reactivate(client, second_client):
    _setup(client)
    staff_id = user_id_by_email(client, STAFF)
    login(second_client, STAFF)

    deactivated = post(client, f"/api/v1/users/{staff_id}/deactivate")
    assert deactivated.status_code == 200 and deactivated.json()["is_active"] is False
    assert second_client.get("/api/v1/auth/me").status_code == 401
    assert login(second_client, STAFF).status_code == 401

    reactivated = post(client, f"/api/v1/users/{staff_id}/reactivate")
    assert reactivated.status_code == 200 and reactivated.json()["is_active"] is True
    assert login(second_client, STAFF).status_code == 200
    assert [row.event_metadata["target_role"] for row in audit_rows(client, "user_disabled")] == ["staff"]
    assert len(audit_rows(client, "user_enabled")) == 1


def test_admin_cannot_deactivate_themselves(client):
    _setup(client)
    response = post(client, f"/api/v1/users/{user_id_by_email(client, ADMIN)}/deactivate")
    assert response.status_code == 409
    assert response.json()["detail"] == "Não pode desativar a própria conta."


def test_last_active_admin_can_never_be_deactivated(client):
    """Defence in depth: through the API the actor is always another active
    admin, so exercise the rule at the service layer too."""
    _setup(client)
    with client.session_factory() as db:
        admin = db.query(User).filter(User.email_matches(ADMIN)).one()
        staff = db.query(User).filter(User.email_matches(STAFF)).one()
        with pytest.raises(HTTPException) as excinfo:
            users_service.deactivate(db, admin, staff)
        assert excinfo.value.status_code == 409
        assert db.get(User, admin.id).is_active is True


def test_another_admin_can_be_deactivated_while_one_remains(client):
    _setup(client)
    other_admin = _second_admin(client)
    assert post(client, f"/api/v1/users/{other_admin}/deactivate").status_code == 200


def test_patient_deactivation_through_the_patients_route_uses_lifecycle_rules(client, second_client):
    clinic = _setup(client)
    login(second_client, PATIENT)
    with client.session_factory() as db:
        patient = db.query(Patient).filter(Patient.clinic_id == uuid.UUID(clinic["id"])).one()
    login(client, ADMIN)
    response = post(client, f"/api/v1/patients/{patient.id}/deactivate")
    assert response.status_code == 200
    assert second_client.get("/api/v1/auth/me").status_code == 401


# --- account listing / MFA reset ----------------------------------------------------------


def test_account_list_hides_patient_contact_data(client, totp_clock):
    _setup(client)
    login(client, STAFF)
    enrol_mfa(client, totp_clock)
    login(client, ADMIN)
    response = client.get("/api/v1/users")
    assert response.status_code == 200
    assert response.headers["X-Total-Count"] == "3"
    by_role = {row["role"]: row for row in response.json()}
    assert by_role["patient"]["email"] is None
    assert by_role["staff"]["email"] == STAFF
    assert by_role["staff"]["staff_role"] == "nurse"
    assert by_role["staff"]["mfa_enabled"] is True
    assert "hashed_password" not in response.text


def test_admin_mfa_reset_forces_re_enrolment(client, second_client, enforce_mfa, totp_clock):
    _setup(client)
    staff_id = user_id_by_email(client, STAFF)
    assert post(client, f"/api/v1/users/{staff_id}/mfa/reset").status_code == 409

    login(second_client, STAFF)
    enrol_mfa(second_client, totp_clock)
    login(client, ADMIN)
    enrol_mfa(client, totp_clock)
    enforce_mfa()
    reset = post(client, f"/api/v1/users/{staff_id}/mfa/reset")
    assert reset.status_code == 200 and reset.json()["mfa_enabled"] is False
    assert second_client.get("/api/v1/auth/me").status_code == 401
    with client.session_factory() as db:
        assert db.get(UserMfa, uuid.UUID(staff_id)) is None
    relogin = login(second_client, STAFF)
    assert relogin.status_code == 200 and relogin.json()["pending_action"] == "mfa_setup"
    assert len(audit_rows(client, "mfa_reset")) == 1


def test_only_clinic_admins_reach_account_administration(client):
    _setup(client)
    staff_id = user_id_by_email(client, STAFF)
    login(client, STAFF)
    assert client.get("/api/v1/users").status_code == 403
    assert post(client, f"/api/v1/users/{staff_id}/deactivate").status_code == 403
    login(client, PATIENT)
    assert client.get("/api/v1/users").status_code == 403


# --- tenant isolation ---------------------------------------------------------------------


def test_admins_cannot_see_or_act_on_another_clinic(client):
    _setup(client)
    staff_a = user_id_by_email(client, STAFF)
    client.cookies.clear()
    onboard_clinic(client, "admin-b@outra.pt", name="Outra Clínica")
    login(client, "admin-b@outra.pt")

    listed = client.get("/api/v1/users").json()
    assert [row["email"] for row in listed] == ["admin-b@outra.pt"]
    for path in ("deactivate", "reactivate", "password-reset", "require-password-change", "mfa/reset"):
        response = post(client, f"/api/v1/users/{staff_a}/{path}")
        assert response.status_code == 404, path
    assert post(client, f"/api/v1/users/{uuid.uuid4()}/deactivate").status_code == 404
    with client.session_factory() as db:
        assert db.get(User, uuid.UUID(staff_a)).is_active is True


# --- e-mail identity ------------------------------------------------------------------------


def test_email_identity_is_case_insensitive(client):
    onboard_clinic(client, ADMIN)
    assert login(client, "  ADMIN@Clinica.PT ").status_code == 200
    duplicate = post(
        client,
        "/api/v1/staff",
        {"full_name": "Duplicado", "email": "Admin@Clinica.pt", "password": PASSWORD, "staff_role": "doctor"},
    )
    assert duplicate.status_code == 400


def test_accounts_stored_before_normalisation_still_log_in(client):
    clinic = onboard_clinic(client, ADMIN)
    with client.session_factory() as db:
        db.add(
            User(
                email="Legado@Clinica.pt",
                hashed_password=hash_password(PASSWORD),
                full_name="Conta Antiga",
                role=UserRole.STAFF,
                clinic_id=uuid.UUID(clinic["id"]),
            )
        )
        db.commit()
    assert login(client, "legado@clinica.pt").status_code == 200


# --- operator recovery of clinic admins -------------------------------------------------------


def test_operator_can_issue_a_reset_link_for_a_locked_out_admin(client, capsys):
    _setup(client)
    assert account_recovery.main(["issue-password-reset", "--email", ADMIN, "--ticket", "INC-42"]) == 0
    out = capsys.readouterr().out
    token = out.strip().splitlines()[-1].split("#token=")[1]
    assert _confirm(client, token).status_code == 204
    assert login(client, ADMIN, NEW_PASSWORD).status_code == 200

    row = audit_rows(client, "password_reset_issued")[-1]
    assert row.actor_user_id is None and row.event_metadata["via"] == "operator"
    assert row.event_metadata["ticket"] == "INC-42"
    assert token not in str(row.event_metadata)


def test_operator_can_reset_a_lost_admin_mfa_device(client, enforce_mfa, totp_clock):
    _setup(client)
    enrol_mfa(client, totp_clock)
    assert login(client, ADMIN).status_code == 202
    enforce_mfa()
    assert account_recovery.main(["reset-mfa", "--email", ADMIN, "--ticket", "INC-43"]) == 0
    relogin = login(client, ADMIN)
    assert relogin.status_code == 200 and relogin.json()["pending_action"] == "mfa_setup"
    assert audit_rows(client, "mfa_reset")[-1].event_metadata["via"] == "operator"


@pytest.mark.parametrize(
    "argv",
    [
        ["issue-password-reset", "--email", STAFF, "--ticket", "INC-1"],
        ["issue-password-reset", "--email", "ninguem@example.com", "--ticket", "INC-1"],
        ["issue-password-reset", "--email", ADMIN, "--ticket", " "],
        ["reset-mfa", "--email", ADMIN, "--ticket", "INC-1"],
    ],
)
def test_operator_recovery_refuses_out_of_scope_requests(client, capsys, argv):
    _setup(client)
    assert account_recovery.main(argv) == 2
    assert "Refused" in capsys.readouterr().err
    with client.session_factory() as db:
        assert db.query(PasswordResetToken).count() == 0


def _second_admin(client) -> str:
    with client.session_factory() as db:
        admin = db.query(User).filter(User.email_matches(ADMIN)).one()
        other = User(
            email="admin2@clinica.pt",
            hashed_password=hash_password(PASSWORD),
            full_name="Segundo Admin",
            role=UserRole.CLINIC_ADMIN,
            clinic_id=admin.clinic_id,
        )
        db.add(other)
        db.commit()
        return str(other.id)
