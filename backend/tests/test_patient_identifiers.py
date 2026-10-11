"""Patient identifiers (NIF, NISS, Nº de utente) and address.

- validation: NIF and NISS check digits, SNS format, postal code 0000-000;
- server-side masking: the API only returns the last three digits;
- "Mostrar": a dedicated reveal endpoint, audited as identifiers viewed (who, when, which patient);
- permissions: assigned doctors/nurses, administrative staff and the clinic administrator manage
  identifiers; the patient sees and reveals their own but cannot change them, and edits only phone
  and address; nobody changes the email here;
- unique NIF per clinic, only when filled in;
- audit rows and logs never contain the values (only field names).

All values are synthetic.
"""

import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.core.pt_identifiers import is_valid_nif, is_valid_niss, is_valid_postal_code, mask
from app.models import AuditAction, AuditLog, AuditResult
from tests.test_authorization_p4_1 import _login, _tenant, _use

NIF = "123456789"  # synthetic, valid check digit
OTHER_NIF = "234567899"  # synthetic, valid check digit
NISS = "12345678902"  # synthetic, valid check digit
SNS = "987654321"
SECRET_VALUES = (NIF, OTHER_NIF, NISS, SNS)


def _identification(tenant: dict) -> str:
    return f"/api/v1/patients/{tenant['patient_id']}/identification"


def _audit(client: TestClient, action: AuditAction) -> list[AuditLog]:
    db = client.session_factory()
    try:
        return db.query(AuditLog).filter(AuditLog.action == action).order_by(AuditLog.timestamp).all()
    finally:
        db.close()


def _row_text(row: AuditLog) -> str:
    return json.dumps(
        {column.name: str(getattr(row, column.key)) for column in AuditLog.__table__.columns}, ensure_ascii=False
    )


def _set_identifiers(client: TestClient, tenant: dict, role: str = "clinic_admin", **values: str | None):
    headers = _use(client, tenant["identities"][role])
    return client.patch(_identification(tenant), headers=headers, json=values)


# --- validation -------------------------------------------------------------------------------


@pytest.mark.parametrize("value", [NIF, OTHER_NIF, "500000000"])
def test_valid_nif(value: str):
    assert is_valid_nif(value)


@pytest.mark.parametrize("value", ["123456788", "12345678", "1234567890", "12345678a", ""])
def test_invalid_nif(value: str):
    assert not is_valid_nif(value)


def test_niss_check_digit():
    assert is_valid_niss(NISS)
    assert not is_valid_niss("12345678900")
    assert not is_valid_niss("32345678903")  # must start with 1 or 2
    assert not is_valid_niss("1234567890")


def test_postal_code_and_mask():
    assert is_valid_postal_code("1000-001")
    for value in ("1000001", "1000-01", "100-0001", "abcd-efg"):
        assert not is_valid_postal_code(value)
    assert mask(NIF) == "••••••789"
    assert mask(None) is None


# --- masking and reveal -------------------------------------------------------------------------


def test_api_returns_only_the_last_three_digits_and_reveal_is_audited(client: TestClient):
    tenant = _tenant(client, "mask")
    assert _set_identifiers(client, tenant, nif=NIF, niss=NISS, national_health_number=SNS).status_code == 200

    for role in ("doctor", "patient"):
        _use(client, tenant["identities"][role])
        detail = client.get(f"/api/v1/patients/{tenant['patient_id']}")
        assert detail.status_code == 200
        assert detail.json()["identifiers"] == {
            "nif": "••••••789",
            "niss": "••••••••902",
            "national_health_number": "••••••321",
        }
        assert "national_health_number" not in detail.json()
        for value in SECRET_VALUES:
            assert value not in detail.text

    for role in ("doctor", "nurse", "admin", "clinic_admin", "patient"):
        headers = _use(client, tenant["identities"][role])
        card = client.get(_identification(tenant))
        assert card.status_code == 200, role
        assert card.json()["identifiers"]["nif"] == "••••••789"
        assert card.json()["can_edit"] is (role != "patient")
        assert NIF not in card.text

        revealed = client.post(f"{_identification(tenant)}/reveal", headers=headers)
        assert revealed.status_code == 200, role
        assert revealed.json() == {"nif": NIF, "niss": NISS, "national_health_number": SNS}
        assert revealed.headers["cache-control"] == "no-store"

    rows = _audit(client, AuditAction.PATIENT_IDENTIFIERS_VIEWED)
    assert len(rows) == 5
    for row in rows:
        assert row.result == AuditResult.SUCCESS
        assert str(row.resource_id) == tenant["patient_id"]
        assert row.resource_type == "patient"
        assert row.actor_user_id is not None and row.timestamp is not None
        text = _row_text(row)
        for value in SECRET_VALUES:
            assert value not in text


def test_reveal_requires_csrf(client: TestClient):
    tenant = _tenant(client, "reveal-csrf")
    _use(client, tenant["identities"]["doctor"])
    assert client.post(f"{_identification(tenant)}/reveal").status_code == 403
    assert _audit(client, AuditAction.PATIENT_IDENTIFIERS_VIEWED) == []


# --- permissions --------------------------------------------------------------------------------


def test_identifier_permissions(client: TestClient):
    tenant = _tenant(client, "perm")
    other = _tenant(client, "perm-other")

    # Assigned doctors and nurses, administrative staff and the clinic administrator may change them.
    for role, nif in (("doctor", NIF), ("nurse", OTHER_NIF), ("admin", NIF), ("clinic_admin", None)):
        response = _set_identifiers(client, tenant, role, nif=nif)
        assert response.status_code == 200, (role, response.text)

    # The patient sees and reveals their own identifiers but never changes them.
    patient_headers = _use(client, tenant["identities"]["patient"])
    assert client.patch(_identification(tenant), headers=patient_headers, json={"nif": NIF}).status_code == 404

    # A doctor without an active care assignment has no access.
    created = client.post(
        "/api/v1/staff",
        headers=_use(client, tenant["identities"]["clinic_admin"]),
        json={
            "full_name": "Doctor Unassigned",
            "email": "doctor-unassigned@example.pt",
            "password": "SenhaForte123!",
            "staff_role": "doctor",
            "require_password_change": False,
        },
    )
    assert created.status_code == 201
    headers = _use(client, _login(client, "doctor-unassigned@example.pt"))
    assert client.get(_identification(tenant)).status_code == 403
    assert client.post(f"{_identification(tenant)}/reveal", headers=headers).status_code == 403
    assert client.patch(_identification(tenant), headers=headers, json={"nif": NIF}).status_code == 403

    # Another clinic's staff and patients never see that the patient exists.
    for role in ("clinic_admin", "admin", "doctor", "patient"):
        headers = _use(client, other["identities"][role])
        assert client.get(_identification(tenant)).status_code == 404
        assert client.post(f"{_identification(tenant)}/reveal", headers=headers).status_code == 404
        assert client.patch(_identification(tenant), headers=headers, json={"nif": NIF}).status_code == 404

    # Administrative roles get the identification card only: the clinical file stays closed.
    for role in ("admin", "clinic_admin"):
        headers = _use(client, tenant["identities"][role])
        assert client.get(f"/api/v1/patients/{tenant['patient_id']}").status_code == 403
        assert client.patch(
            f"/api/v1/patients/{tenant['patient_id']}", headers=headers, json={"address_locality": "Lisboa"}
        ).status_code == 403
        assert client.get(f"/api/v1/patients/{tenant['patient_id']}/medical-records").status_code == 403

    denied = _audit(client, AuditAction.PERMISSION_DENIED)
    assert any(row.resource_type == "patient_identifiers" for row in denied)


def test_patient_edits_only_phone_and_address_never_email(client: TestClient):
    tenant = _tenant(client, "contact")
    url = f"/api/v1/patients/{tenant['patient_id']}"
    headers = _use(client, tenant["identities"]["patient"])
    changed = client.patch(
        url,
        headers=headers,
        json={
            "phone": "912345678",
            "address_street": "Rua Sintética, 1",
            "address_postal_code": "1000-001",
            "address_locality": "Lisboa",
        },
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["address"] == {"street": "Rua Sintética, 1", "postal_code": "1000-001", "locality": "Lisboa"}
    assert changed.json()["phone"] == "912345678"

    assert client.patch(url, headers=headers, json={"birth_date": "2000-01-01"}).status_code == 403
    for payload in ({"email": "new@example.pt"}, {"nif": NIF}, {"national_health_number": SNS}):
        assert client.patch(url, headers=headers, json=payload).status_code == 422

    rows = _audit(client, AuditAction.PATIENT_UPDATED)
    assert rows[-1].event_metadata["fields"] == ["address_locality", "address_postal_code", "address_street", "phone"]
    text = _row_text(rows[-1])
    assert "Rua Sintética" not in text and "912345678" not in text

    # Clinicians also manage the address; administrative roles do not.
    doctor_headers = _use(client, tenant["identities"]["doctor"])
    assert client.patch(url, headers=doctor_headers, json={"address_locality": "Porto"}).status_code == 200


# --- validation through the API -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "field", "message"),
    [
        ({"nif": "123456788"}, "nif", "NIF inválido"),
        ({"niss": "12345678900"}, "niss", "NISS inválido"),
        ({"national_health_number": "12345"}, "national_health_number", "9 dígitos"),
    ],
)
def test_invalid_identifiers_are_rejected_without_echoing_the_value(client: TestClient, payload, field, message):
    tenant = _tenant(client, f"invalid-{field}")
    response = _set_identifiers(client, tenant, **payload)
    assert response.status_code == 422
    (error,) = response.json()["detail"]
    assert error["loc"][-1] == field
    assert message in error["msg"]
    assert "input" not in error
    assert list(payload.values())[0] not in response.text


def test_postal_code_format_is_validated(client: TestClient):
    tenant = _tenant(client, "postal")
    headers = _use(client, tenant["identities"]["patient"])
    response = client.patch(
        f"/api/v1/patients/{tenant['patient_id']}", headers=headers, json={"address_postal_code": "1000001"}
    )
    assert response.status_code == 422
    assert "0000-000" in response.json()["detail"][0]["msg"]


def test_spaced_input_is_normalised(client: TestClient):
    tenant = _tenant(client, "spaced")
    assert _set_identifiers(client, tenant, nif="123 456 789").status_code == 200
    headers = _use(client, tenant["identities"]["clinic_admin"])
    assert client.post(f"{_identification(tenant)}/reveal", headers=headers).json()["nif"] == NIF


# --- unique NIF per clinic ----------------------------------------------------------------------


def test_nif_is_unique_per_clinic_only_when_filled(client: TestClient):
    first = _tenant(client, "nif-a")
    assert _set_identifiers(client, first, nif=NIF).status_code == 200

    # A second patient in the same clinic cannot take the same NIF.
    registered = client.post(
        "/api/v1/patients/register",
        json={
            "clinic_id": first["clinic_id"],
            "full_name": "Second Patient",
            "email": "second-nif@example.pt",
            "password": "SenhaForte123!",
        },
    )
    assert registered.status_code == 201
    second_id = registered.json()["id"]
    headers = _use(client, first["identities"]["clinic_admin"])
    duplicate = client.patch(f"/api/v1/patients/{second_id}/identification", headers=headers, json={"nif": NIF})
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "Já existe um paciente nesta clínica com este NIF."
    assert NIF not in duplicate.text

    # Empty NIFs never collide, and saving the same NIF again on the same patient is fine.
    assert client.patch(f"/api/v1/patients/{second_id}/identification", headers=headers, json={"nif": None}).status_code == 200
    assert _set_identifiers(client, first, nif=NIF).status_code == 200

    # Another clinic may hold the same NIF for its own patient.
    other = _tenant(client, "nif-b")
    assert _set_identifiers(client, other, nif=NIF).status_code == 200


# --- audit and logs never hold the values ------------------------------------------------------------


def test_changes_are_audited_by_field_name_and_values_never_reach_logs(client: TestClient, caplog):
    tenant = _tenant(client, "audit")
    with caplog.at_level(logging.DEBUG):
        assert _set_identifiers(client, tenant, "doctor", nif=NIF, niss=NISS).status_code == 200
        assert _set_identifiers(client, tenant, "admin", national_health_number=SNS, nif=NIF).status_code == 200
        headers = _use(client, tenant["identities"]["doctor"])
        client.post(f"{_identification(tenant)}/reveal", headers=headers)
        _set_identifiers(client, tenant, nif="123456788")  # rejected
        registered = client.post(
            "/api/v1/patients/register",
            json={"clinic_id": tenant["clinic_id"], "full_name": "Dup", "email": "dup@example.pt", "password": "SenhaForte123!"},
        )
        _use(client, tenant["identities"]["clinic_admin"])
        client.patch(
            f"/api/v1/patients/{registered.json()['id']}/identification",
            headers=_use(client, tenant["identities"]["clinic_admin"]),
            json={"nif": NIF},
        )

    rows = _audit(client, AuditAction.PATIENT_IDENTIFIERS_UPDATED)
    assert [row.event_metadata["fields"] for row in rows] == [["nif", "niss"], ["national_health_number"]]
    for row in rows:
        assert str(row.resource_id) == tenant["patient_id"]
        text = _row_text(row)
        for value in SECRET_VALUES:
            assert value not in text

    logged = "\n".join(record.getMessage() for record in caplog.records)
    # The application's own request log was captured, so the check below is meaningful.
    assert "/identification" in logged
    for value in (*SECRET_VALUES, "123456788"):
        assert value not in logged
