import uuid
from io import BytesIO

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models import AuditAction, AuditLog, Notification
from app.modules.documents.service import NEW_DOCUMENT_NOTIFICATION_MESSAGE, NEW_DOCUMENT_NOTIFICATION_TITLE
from app.modules.documents.storage import LocalDocumentStorage
from tests.phase1_world import fresh_patient


def _upload(
    actor,
    patient_id: str,
    name: str = "report.pdf",
    content: bytes = b"%PDF-1.7\ncontent",
    title: str | None = "Análises de rotina",
):
    return actor.client.post(
        f"/api/v1/patients/{patient_id}/documents",
        data={} if title is None else {"title": title},
        files={"file": (name, content, "application/pdf")},
        headers={settings.CSRF_HEADER_NAME: actor.csrf_token or ""},
    )


def _denials(world, actor, path: str) -> list[AuditLog]:
    with world.db() as db:
        rows = db.scalars(
            select(AuditLog).where(
                AuditLog.action == AuditAction.PERMISSION_DENIED,
                AuditLog.actor_user_id == uuid.UUID(actor.user_id),
            )
        ).all()
        return [row for row in rows if (row.event_metadata or {}).get("path") == path]


def test_document_upload_list_download_and_append_only(world, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_DIR", str(tmp_path))
    doctor = world.a.doctor
    # Deterministic: a fresh patient on the doctor's care team, so the exact-list
    # assertions below never depend on uploads made by other tests in this module.
    patient = fresh_patient(world, world.a, "docs-append-only")
    assigned = world.a.admin.post(
        f"/api/v1/patients/{patient.patient_id}/care-team", json={"staff_id": doctor.staff_id}
    )
    assert assigned.status_code == 201, assigned.text
    patient_id = patient.patient_id
    uploaded = _upload(doctor, patient_id, title="  Análises de rotina  ")
    assert uploaded.status_code == 201, uploaded.text
    metadata = uploaded.json()
    assert metadata["title"] == "Análises de rotina"  # D5: custom title, trimmed
    assert metadata["original_filename"] == "report.pdf"
    assert metadata["content_type"] == "application/pdf"
    assert "storage_key" not in metadata
    storage = LocalDocumentStorage(tmp_path)
    assert storage.exists(next(tmp_path.iterdir()).name)

    listing = doctor.get(f"/api/v1/patients/{patient_id}/documents")
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()] == [metadata["id"]]
    assert listing.headers["x-total-count"] == "1"

    download = doctor.get(f"/api/v1/documents/{metadata['id']}/download")
    assert download.status_code == 200
    assert download.content == b"%PDF-1.7\ncontent"
    assert download.headers["content-type"].startswith("application/pdf")
    assert "filename*=UTF-8''report.pdf" in download.headers["content-disposition"]

    # D3: append-only. There is no delete route; the file and the row stay.
    removed = doctor.call("DELETE", f"/api/v1/documents/{metadata['id']}")
    assert removed.status_code in {404, 405}
    assert len(list(tmp_path.iterdir())) == 1
    assert doctor.get(f"/api/v1/documents/{metadata['id']}/download").status_code == 200
    with world.db() as db:
        actions = set(
            db.scalars(
                select(AuditLog.action).where(
                    AuditLog.resource_id == metadata["id"],
                    AuditLog.action.in_(
                        [
                            AuditAction.DOCUMENT_UPLOADED,
                            AuditAction.DOCUMENT_DOWNLOADED,
                            AuditAction.DOCUMENT_DELETED,
                        ]
                    ),
                )
            )
        )
    assert actions == {AuditAction.DOCUMENT_UPLOADED, AuditAction.DOCUMENT_DOWNLOADED}


def test_document_shows_uploader_name_never_internal_user_ids(world, tmp_path, monkeypatch):
    """D2: staff and patient views carry the uploader's display name, never a raw user id."""
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_DIR", str(tmp_path))
    doctor = world.a.doctor
    patient = world.a.patients["a2"]
    created = _upload(doctor, patient.patient_id)
    assert created.status_code == 201, created.text
    doctor_name = doctor.load_identity()["full_name"]
    for actor in (doctor, patient):
        listing = actor.get(f"/api/v1/patients/{patient.patient_id}/documents")
        assert listing.status_code == 200, listing.text
        item = next(i for i in listing.json() if i["id"] == created.json()["id"])
        assert item["uploaded_by_name"] == doctor_name
        assert "uploaded_by_user_id" not in item
        assert doctor.user_id not in listing.text


def test_staff_upload_notifies_the_patient_generically_with_a_deep_link(world, tmp_path, monkeypatch):
    """D4: the patient is told a document exists, with no title or filename, and a target id."""
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_DIR", str(tmp_path))
    patient = world.a.patients["a2"]
    created = _upload(world.a.nurse, patient.patient_id, name="biopsia.pdf", title="Biópsia confidencial")
    assert created.status_code == 201, created.text
    with world.db() as db:
        rows = db.scalars(
            select(Notification).where(
                Notification.user_id == uuid.UUID(patient.user_id),
                Notification.target_id == uuid.UUID(created.json()["id"]),
            )
        ).all()
    assert len(rows) == 1
    notification = rows[0]
    assert notification.target_type == "document"
    assert notification.conversation_target_id is None
    assert (notification.title, notification.message) == (
        NEW_DOCUMENT_NOTIFICATION_TITLE,
        NEW_DOCUMENT_NOTIFICATION_MESSAGE,
    )
    assert "iópsia" not in notification.title + notification.message
    api_view = patient.get("/api/v1/notifications").json()
    assert any(n["target_type"] == "document" and n["target_id"] == created.json()["id"] for n in api_view)


@pytest.mark.parametrize(("data", "label"), [({}, "missing"), ({"title": "   "}, "blank"), ({"title": "x" * 201}, "long")])
def test_document_upload_requires_a_title(world, tmp_path, monkeypatch, data, label):
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_DIR", str(tmp_path))
    actor = world.a.doctor
    response = actor.client.post(
        f"/api/v1/patients/{world.a.patients['a1'].patient_id}/documents",
        data=data,
        files={"file": ("report.pdf", b"%PDF-1.7\ncontent", "application/pdf")},
        headers={settings.CSRF_HEADER_NAME: actor.csrf_token or ""},
    )
    assert response.status_code == 422, label
    assert not list(tmp_path.iterdir())


def test_document_authorization_and_tenant_isolation(world, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_DIR", str(tmp_path))
    foreign_patient = world.b.patients["b1"].patient_id
    own_patient = world.a.patients["a1"]
    upload_path = "/api/v1/patients/{}/documents"

    def denied_once(actor, path: str, resource_id: str, *, expected_total: int = 1) -> None:
        # D1: every refusal leaves exactly one PERMISSION_DENIED row, under the actor's clinic.
        # (Upload and list share a URL path, so the second refusal on it makes the total 2.)
        rows = sorted(_denials(world, actor, path), key=lambda row: row.timestamp)
        assert len(rows) == expected_total, (actor.key, path, len(rows))
        assert str(rows[-1].resource_id) == resource_id
        assert str(rows[-1].clinic_id) == actor.clinic_id

    assert _upload(world.a.doctor, foreign_patient).status_code == 404
    denied_once(world.a.doctor, upload_path.format(foreign_patient), foreign_patient)
    assert _upload(world.a.staff_admin, own_patient.patient_id).status_code == 403
    denied_once(world.a.staff_admin, upload_path.format(own_patient.patient_id), own_patient.patient_id)
    # Patients never get a write action on their own record; the central policy answers 404
    # (same as an unknown patient) rather than confirming the action exists for them.
    assert _upload(own_patient, own_patient.patient_id).status_code == 404
    denied_once(own_patient, upload_path.format(own_patient.patient_id), own_patient.patient_id)

    created = _upload(world.b.doctor, foreign_patient)
    assert created.status_code == 201, created.text
    document_id = created.json()["id"]
    download_path = f"/api/v1/documents/{document_id}/download"
    assert world.a.doctor.get(download_path).status_code == 404
    denied_once(world.a.doctor, download_path, document_id)
    # D3: no delete route exists at all, for any caller.
    assert world.a.doctor.call("DELETE", f"/api/v1/documents/{document_id}").status_code in {404, 405}
    assert world.b.doctor.call("DELETE", f"/api/v1/documents/{document_id}").status_code in {404, 405}
    list_path = f"/api/v1/patients/{foreign_patient}/documents"
    assert world.a.doctor.get(list_path).status_code == 404
    denied_once(world.a.doctor, list_path, foreign_patient, expected_total=2)
    assert world.b.doctor.get(f"/api/v1/documents/{document_id}/download").status_code == 200


def test_document_routes_require_authentication(world):
    anonymous = world.a.doctor.client.__class__(world.a.doctor.client.app)
    patient_id = world.a.patients["a1"].patient_id
    assert anonymous.get(f"/api/v1/patients/{patient_id}/documents").status_code == 401
    assert (
        anonymous.post(
            f"/api/v1/patients/{patient_id}/documents",
            data={"title": "A"},
            files={"file": ("a.pdf", b"%PDF-1.7", "application/pdf")},
        ).status_code
        == 401
    )
    assert anonymous.get(f"/api/v1/documents/{uuid.uuid4()}/download").status_code == 401


@pytest.mark.parametrize(
    ("filename", "content", "mime"),
    [
        ("script.pdf", b"#!/bin/sh", "application/pdf"),
        ("bad.exe", b"MZ", "application/octet-stream"),
        ("../escape.pdf", b"%PDF-1.7", "application/pdf"),
        ("empty.pdf", b"", "application/pdf"),
    ],
)
def test_document_upload_rejects_invalid_content(world, filename, content, mime):
    actor = world.a.doctor
    response = actor.client.post(
        f"/api/v1/patients/{world.a.patients['a1'].patient_id}/documents",
        data={"title": "Conteúdo inválido"},
        files={"file": (filename, content, mime)},
        headers={settings.CSRF_HEADER_NAME: actor.csrf_token or ""},
    )
    assert response.status_code == 422


def test_document_upload_enforces_configured_maximum(world, monkeypatch):
    monkeypatch.setattr(settings, "DOCUMENT_MAX_UPLOAD_BYTES", 1024)
    response = _upload(
        world.a.doctor,
        world.a.patients["a1"].patient_id,
        content=b"%PDF-1.7" + b"x" * 1024,
    )
    assert response.status_code == 413


def test_document_upload_larger_than_the_generic_body_cap_is_accepted(world, tmp_path, monkeypatch):
    """The documents route is exempt from MAX_REQUEST_BODY_BYTES (1 MiB) up to
    DOCUMENT_MAX_UPLOAD_BYTES; every other route keeps the generic cap."""
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_DIR", str(tmp_path))
    big = b"%PDF-1.7\n" + b"x" * (settings.MAX_REQUEST_BODY_BYTES + 512 * 1024)
    assert len(big) < settings.DOCUMENT_MAX_UPLOAD_BYTES
    response = _upload(world.a.doctor, world.a.patients["a1"].patient_id, content=big)
    assert response.status_code == 201, response.text
    oversized_json = world.a.doctor.client.post(
        "/api/v1/appointments",
        content=b"{\"x\": \"" + b"y" * settings.MAX_REQUEST_BODY_BYTES + b"\"}",
        headers={"Content-Type": "application/json", settings.CSRF_HEADER_NAME: world.a.doctor.csrf_token or ""},
    )
    assert oversized_json.status_code == 413


@pytest.mark.parametrize(
    ("filename", "content", "mime"),
    [
        ("scan.png", b"\x89PNG\r\n\x1a\nminimal", "image/png"),
        ("scan.jpg", b"\xff\xd8\xff\xd9", "image/jpeg"),
    ],
)
def test_document_upload_accepts_supported_images(world, tmp_path, monkeypatch, filename, content, mime):
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_DIR", str(tmp_path))
    actor = world.a.doctor
    response = actor.client.post(
        f"/api/v1/patients/{world.a.patients['a1'].patient_id}/documents",
        data={"title": "Imagem"},
        files={"file": (filename, content, mime)},
        headers={settings.CSRF_HEADER_NAME: actor.csrf_token or ""},
    )
    assert response.status_code == 201, response.text
    assert response.json()["content_type"] == mime


def test_document_upload_rejects_missing_file(world):
    actor = world.a.doctor
    response = actor.client.post(
        f"/api/v1/patients/{world.a.patients['a1'].patient_id}/documents",
        data={"title": "Sem ficheiro"},
        headers={settings.CSRF_HEADER_NAME: actor.csrf_token or ""},
    )
    assert response.status_code == 422


def test_private_storage_rejects_path_keys_and_does_not_overwrite(tmp_path):
    storage = LocalDocumentStorage(tmp_path)
    key = storage.new_key()
    storage.save(key, BytesIO(b"safe"))
    with pytest.raises(FileExistsError):
        storage.save(key, BytesIO(b"overwrite"))
    with pytest.raises(ValueError):
        storage.open("../escape")
    assert storage.open(key).read() == b"safe"
