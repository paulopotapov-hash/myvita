"""Patient profile photo with the doctor's approval.

- Validation by content (JPEG/PNG only, 5 MB, real image, 200x200, in colour), EXIF/GPS
  removed, 512x512 output.
- Permissions: the patient, the associated doctor, a doctor not associated, other roles,
  another clinic.
- Pending -> approved / rejected, replacement and removal, with immediate deletion of
  the image (file and row) and a reliable retry when the file deletion fails.
- Notifications and identifiers-only audit.
Synthetic images only.
"""

import io
import uuid

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import settings
from app.jobs import run_once
from app.models import AuditAction, AuditLog, Notification, PatientPhoto, PatientPhotoStatus, StorageDeletion
from app.modules.documents.storage import LocalDocumentStorage
from app.modules.patient_photos.images import NOT_AN_IMAGE, NOT_IN_COLOUR, TOO_LARGE, TOO_SMALL
from tests.clinical_support import Tenant, make_tenant

URL = "/api/v1/patient-photos"


@pytest.fixture()
def tenant(client: TestClient) -> Tenant:
    return make_tenant(client, f"photo-{uuid.uuid4().hex[:8]}")


def _image(fmt: str = "JPEG", size: tuple[int, int] = (800, 600), colour: tuple[int, int, int] = (190, 120, 90), mode: str = "RGB", **save) -> bytes:
    image = Image.new(mode, size, colour if mode in ("RGB", "RGBA") else colour[0])
    out = io.BytesIO()
    image.save(out, fmt, **save)
    return out.getvalue()


def _upload(client: TestClient, tenant: Tenant, data: bytes, who: str = "patient", name: str = "foto.jpg", content_type: str = "image/jpeg"):
    return client.post(URL, headers=tenant.act(client, who), files={"file": (name, data, content_type)})


def _pending_id(client: TestClient, tenant: Tenant, who: str = "patient") -> str:
    tenant.act(client, who)
    return client.get(f"{URL}/mine").json()["pending"]["id"]


def _row(client: TestClient, photo_id: str) -> PatientPhoto | None:
    with client.session_factory() as db:  # type: ignore[attr-defined]
        return db.get(PatientPhoto, uuid.UUID(photo_id))


def _stored(key: str) -> bool:
    return LocalDocumentStorage(settings.DOCUMENT_STORAGE_DIR).exists(key)


def _audit(client: TestClient, *actions: AuditAction) -> list[AuditLog]:
    with client.session_factory() as db:  # type: ignore[attr-defined]
        return db.query(AuditLog).filter(AuditLog.action.in_(actions)).order_by(AuditLog.timestamp).all()


def _titles(client: TestClient, user_id: str) -> list[Notification]:
    with client.session_factory() as db:  # type: ignore[attr-defined]
        return db.query(Notification).filter_by(user_id=uuid.UUID(user_id)).all()


# --- validation ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "name", "content_type", "expected"),
    [
        (b"not an image at all, just text" * 10, "foto.jpg", "image/jpeg", NOT_AN_IMAGE),  # renamed text
        (b"%PDF-1.7\n" + b"0" * 2000, "foto.png", "image/png", NOT_AN_IMAGE),  # a PDF
        (b"\xff\xd8\xff\xe0" + b"\x00" * 3000, "foto.jpg", "image/jpeg", NOT_AN_IMAGE),  # JPEG signature, corrupt body
        (_image("GIF"), "foto.gif", "image/gif", NOT_AN_IMAGE),  # GIF is not accepted
        (_image(size=(150, 150)), "foto.jpg", "image/jpeg", TOO_SMALL),
        (_image("PNG", mode="L", colour=(128, 0, 0)), "foto.png", "image/png", NOT_IN_COLOUR),  # black and white
        (_image(colour=(90, 90, 90)), "foto.jpg", "image/jpeg", NOT_IN_COLOUR),  # grey in RGB
    ],
)
def test_only_real_colour_jpeg_or_png_photos_are_accepted(client: TestClient, tenant: Tenant, data, name, content_type, expected):
    response = _upload(client, tenant, data, name=name, content_type=content_type)
    assert response.status_code == 422 and response.json()["detail"] == expected
    with client.session_factory() as db:  # type: ignore[attr-defined]
        assert db.query(PatientPhoto).filter_by(patient_id=uuid.UUID(tenant.patient_id)).count() == 0


def test_more_than_5_mb_is_refused(client: TestClient, tenant: Tenant):
    big = _image() + b"\x00" * (5 * 1024 * 1024)
    response = _upload(client, tenant, big)
    assert response.status_code == 413 and response.json()["detail"] == TOO_LARGE


def test_a_png_with_transparency_is_accepted_as_a_jpeg(client: TestClient, tenant: Tenant):
    response = _upload(client, tenant, _image("PNG", mode="RGBA", colour=(200, 80, 60, 255), size=(400, 300)), name="foto.png", content_type="image/png")
    assert response.status_code == 201, response.text
    image = client.get(f"{URL}/{response.json()['pending']['id']}/image")
    assert image.headers["content-type"] == "image/jpeg"


def test_exif_and_location_are_removed_and_the_photo_is_512_square(client: TestClient, tenant: Tenant):
    exif = Image.Exif()
    exif[0x0112] = 6  # orientation: rotated
    exif[0x010F] = "Synthetic Camera Maker"
    exif[0x8825] = {1: "N", 2: (38.0, 43.0, 1.5), 3: "W", 4: (9.0, 8.0, 2.5)}  # GPS
    original = _image(size=(1200, 900), exif=exif.tobytes())
    assert b"Synthetic Camera Maker" in original
    response = _upload(client, tenant, original)
    assert response.status_code == 201, response.text
    stored = client.get(f"{URL}/{response.json()['pending']['id']}/image")
    assert stored.status_code == 200
    assert "no-store" in stored.headers["cache-control"] and stored.headers["x-content-type-options"] == "nosniff"
    assert "foto.jpg" in stored.headers["content-disposition"]
    image = Image.open(io.BytesIO(stored.content))
    assert (image.format, image.size) == ("JPEG", (512, 512))
    assert dict(image.getexif()) == {}
    assert b"Exif" not in stored.content and b"Synthetic Camera Maker" not in stored.content
    assert "icc_profile" not in image.info


# --- the flow -------------------------------------------------------------------------------------


def test_pending_then_approved_then_replaced(client: TestClient, tenant: Tenant):
    first = _upload(client, tenant, _image())
    assert first.status_code == 201
    body = first.json()
    assert body["pending"] and body["approved"] is None and body["requirements"][0] == "A cores."
    first_id = body["pending"]["id"]

    # The doctor is told, with a link to the patient; staff still see no photo.
    [submitted] = [n for n in _titles(client, tenant.user_ids["doctor"]) if n.title == "Foto de perfil por aprovar"]
    assert str(submitted.patient_target_id) == tenant.patient_id
    assert _titles(client, tenant.user_ids["nurse"]) == [] or all(n.title != "Foto de perfil por aprovar" for n in _titles(client, tenant.user_ids["nurse"]))
    tenant.act(client, "doctor")
    staff_view = client.get(f"{URL}/patients/{tenant.patient_id}").json()
    assert staff_view == {"approved": None, "pending": {"id": first_id, "created_at": staff_view["pending"]["created_at"]}, "can_review": True}
    assert client.get(f"{URL}/pending-count").json() == {"count": 1}
    tenant.act(client, "nurse")
    assert client.get(f"{URL}/patients/{tenant.patient_id}").json() == {"approved": None, "pending": None, "can_review": False}
    assert client.get(f"{URL}/{first_id}/image").status_code == 404  # pending: initials for the team
    assert client.get(f"{URL}/pending-count").json() == {"count": 0}

    approved = client.post(f"{URL}/{first_id}/approve", headers=tenant.act(client, "doctor"))
    assert approved.status_code == 200 and approved.json()["approved"]["id"] == first_id
    assert client.get(f"{URL}/pending-count").json() == {"count": 0}
    assert any(n.title == "Foto de perfil aprovada" for n in _titles(client, tenant.user_ids["patient"]))
    tenant.act(client, "nurse")
    assert client.get(f"{URL}/{first_id}/image").status_code == 200  # approved: the whole team

    # A new photo is pending; the approved one stays in use until the new one is approved.
    first_key = _row(client, first_id).storage_key
    second = _upload(client, tenant, _image(colour=(60, 140, 200)))
    second_id = second.json()["pending"]["id"]
    assert second.json()["approved"]["id"] == first_id
    tenant.act(client, "nurse")
    assert client.get(f"{URL}/patients/{tenant.patient_id}").json()["approved"]["id"] == first_id

    assert client.post(f"{URL}/{second_id}/approve", headers=tenant.act(client, "doctor")).status_code == 200
    assert _row(client, first_id) is None and not _stored(first_key)  # gone for good
    [deleted] = _audit(client, AuditAction.PATIENT_PHOTO_DELETED)
    assert str(deleted.resource_id) == first_id and deleted.event_metadata == {
        "patient_id": tenant.patient_id, "operation": "superseded", "actor_staff_role": "doctor",
    }


def test_a_newer_upload_replaces_a_pending_one(client: TestClient, tenant: Tenant):
    first_id = _upload(client, tenant, _image()).json()["pending"]["id"]
    first_key = _row(client, first_id).storage_key
    second = _upload(client, tenant, _image(colour=(30, 160, 90)))
    assert second.json()["pending"]["id"] != first_id
    assert _row(client, first_id) is None and not _stored(first_key)


def test_rejection_deletes_the_image_and_keeps_the_reason_until_the_next_upload(client: TestClient, tenant: Tenant):
    photo_id = _upload(client, tenant, _image()).json()["pending"]["id"]
    key = _row(client, photo_id).storage_key
    headers = tenant.act(client, "doctor")
    assert client.post(f"{URL}/{photo_id}/reject", headers=headers, json={"reason": "  "}).status_code == 422
    rejected = client.post(f"{URL}/{photo_id}/reject", headers=headers, json={"reason": "O rosto não está visível."})
    assert rejected.status_code == 200 and rejected.json()["pending"] is None
    row = _row(client, photo_id)
    assert row.status == PatientPhotoStatus.REJECTED and row.storage_key is None and not _stored(key)

    tenant.act(client, "patient")
    mine = client.get(f"{URL}/mine").json()
    assert mine["rejected"]["reason"] == "O rosto não está visível." and mine["pending"] is None
    assert client.get(f"{URL}/{photo_id}/image").status_code == 404
    [notice] = [n for n in _titles(client, tenant.user_ids["patient"]) if n.title == "Foto de perfil não aprovada"]
    assert "rosto" not in notice.message  # generic text; the reason is in the profile
    audit_text = str([row.event_metadata for row in _audit(client, AuditAction.PATIENT_PHOTO_REJECTED, AuditAction.PATIENT_PHOTO_DELETED)])
    assert "rosto" not in audit_text and "foto.jpg" not in audit_text

    _upload(client, tenant, _image(colour=(200, 60, 60)))
    tenant.act(client, "patient")
    assert client.get(f"{URL}/mine").json()["rejected"] is None
    assert _row(client, photo_id) is None


def test_the_patient_removes_their_photo(client: TestClient, tenant: Tenant):
    photo_id = _upload(client, tenant, _image()).json()["pending"]["id"]
    client.post(f"{URL}/{photo_id}/approve", headers=tenant.act(client, "doctor"))
    key = _row(client, photo_id).storage_key
    removed = client.post(f"{URL}/{photo_id}/remove", headers=tenant.act(client, "patient"))
    assert removed.status_code == 200 and removed.json()["approved"] is None
    assert _row(client, photo_id) is None and not _stored(key)
    tenant.act(client, "doctor")
    assert client.get(f"{URL}/patients/{tenant.patient_id}").json()["approved"] is None
    assert [str(row.resource_id) for row in _audit(client, AuditAction.PATIENT_PHOTO_REMOVED)] == [photo_id]
    assert [row.event_metadata["operation"] for row in _audit(client, AuditAction.PATIENT_PHOTO_DELETED)] == ["removed"]


def test_a_failed_file_deletion_is_retried_by_the_background_job(client: TestClient, tenant: Tenant, monkeypatch):
    first_id = _upload(client, tenant, _image()).json()["pending"]["id"]
    client.post(f"{URL}/{first_id}/approve", headers=tenant.act(client, "doctor"))
    first_key = _row(client, first_id).storage_key
    second_id = _upload(client, tenant, _image(colour=(40, 90, 210))).json()["pending"]["id"]

    def broken(self, key):
        raise PermissionError("synthetic")

    monkeypatch.setattr(LocalDocumentStorage, "delete", broken)
    assert client.post(f"{URL}/{second_id}/approve", headers=tenant.act(client, "doctor")).status_code == 200
    assert _row(client, first_id) is None  # the record is gone at once...
    assert _stored(first_key)  # ...the file is still there, queued
    with client.session_factory() as db:  # type: ignore[attr-defined]
        queued = db.get(StorageDeletion, first_key)
        assert queued.deleted_at is None and queued.attempts == 1

    monkeypatch.undo()
    with client.session_factory() as db:  # type: ignore[attr-defined]
        assert run_once(db).deleted_files == 1
    assert not _stored(first_key)
    with client.session_factory() as db:  # type: ignore[attr-defined]
        done = db.get(StorageDeletion, first_key)
        assert done.deleted_at is not None and done.attempts == 2


# --- permissions --------------------------------------------------------------------------------


def test_permissions(client: TestClient, tenant: Tenant):
    other = make_tenant(client, f"photo-other-{uuid.uuid4().hex[:6]}")
    # tenant.patient has the doctor and nurse on the care team; other_patient has nobody.
    mine_id = _upload(client, tenant, _image()).json()["pending"]["id"]
    theirs_id = _upload(client, tenant, _image(), who="other_patient").json()["pending"]["id"]

    # Staff never upload; only the patient manages their photo.
    assert _upload(client, tenant, _image(), who="doctor").status_code == 403

    # Another patient sees nothing of it.
    headers = tenant.act(client, "other_patient")
    assert client.get(f"{URL}/{mine_id}/image").status_code == 404
    assert client.post(f"{URL}/{mine_id}/remove", headers=headers).status_code == 404
    assert client.post(f"{URL}/{mine_id}/approve", headers=headers).status_code == 403

    # A doctor not associated with the patient neither reviews nor sees it.
    headers = tenant.act(client, "doctor")
    assert client.post(f"{URL}/{theirs_id}/approve", headers=headers).status_code == 403
    assert client.get(f"{URL}/{theirs_id}/image").status_code == 403
    assert client.get(f"{URL}/patients/{tenant.other_patient_id}").status_code == 403

    # Other roles never approve, even on the care team.
    for role in ("nurse", "admin", "clinic_admin", "physiotherapist"):
        response = client.post(f"{URL}/{mine_id}/approve", headers=tenant.act(client, role))
        assert response.status_code == 403, role
        assert client.post(f"{URL}/{mine_id}/reject", headers=tenant.act(client, role), json={"reason": "X"}).status_code == 403, role

    # Another clinic: it does not exist.
    for role in ("doctor", "clinic_admin", "patient"):
        headers = other.act(client, role)
        assert client.get(f"{URL}/{mine_id}/image").status_code == 404, role
        assert client.post(f"{URL}/{mine_id}/approve", headers=headers).status_code == 404, role

    # The associated doctor may; then a decided photo cannot be decided again.
    assert client.post(f"{URL}/{mine_id}/approve", headers=tenant.act(client, "doctor")).status_code == 200
    assert client.post(f"{URL}/{mine_id}/reject", headers=tenant.act(client, "doctor"), json={"reason": "X"}).status_code == 409
    denied = _audit(client, AuditAction.PERMISSION_DENIED)
    assert any(row.resource_type == "patient_photo" for row in denied)


def test_uploads_are_rate_limited_per_user(client: TestClient, tenant: Tenant):
    statuses = [_upload(client, tenant, _image(colour=(100 + index * 10, 60, 40))).status_code for index in range(6)]
    assert statuses == [201] * 5 + [429]
    assert _upload(client, tenant, _image(), who="other_patient").status_code == 201  # same IP, another user
