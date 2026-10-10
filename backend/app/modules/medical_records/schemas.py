import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

from app.core.schemas import RequestModel
from app.models.medical_record import MedicalRecordVisibility


class MedicalRecordContent(RequestModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=20_000)

    @field_validator("title", "content")
    @classmethod
    def non_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class MedicalRecordCreateRequest(MedicalRecordContent):
    # P2.5: internal by default. True is the author's explicit decision to share
    # the new record with the patient (audited and notified like a later share).
    share_with_patient: bool = False


class MedicalRecordUpdateRequest(MedicalRecordContent):
    """Content edit only. Visibility changes go through /share and /unshare, so an
    edit can never change who sees the record; a visibility field here is a 422."""

    expected_version: int = Field(ge=1)


class MedicalRecordVisibilityRequest(RequestModel):
    """The version the professional reviewed: sharing never publishes content they have not seen."""

    expected_version: int = Field(ge=1)


class MedicalRecordPublic(BaseModel):
    """Professional view of a record (internal or shared)."""

    view: Literal["staff"] = "staff"
    id: uuid.UUID
    clinic_id: uuid.UUID
    patient_id: uuid.UUID
    author_staff_id: uuid.UUID
    # Display name for the UI (staff and patient views never show raw ids).
    author_name: str
    title: str
    content: str
    visibility: MedicalRecordVisibility
    # Last explicit share/unshare decision; null for new and legacy records.
    visibility_changed_at: datetime | None
    visibility_changed_by_name: str | None
    version: int
    created_at: datetime
    updated_at: datetime


class MedicalRecordPatientView(BaseModel):
    """Patient view: only records shared with the patient, without internal staff ids,
    versions or sharing metadata."""

    view: Literal["patient"] = "patient"
    id: uuid.UUID
    author_name: str
    title: str
    content: str
    created_at: datetime
    updated_at: datetime


MedicalRecordOut = Annotated[MedicalRecordPublic | MedicalRecordPatientView, Field(discriminator="view")]


class MedicalRecordRevisionPublic(BaseModel):
    """Staff only: the edit and sharing history of a record."""

    id: uuid.UUID
    record_id: uuid.UUID
    editor_staff_id: uuid.UUID
    editor_name: str
    version: int
    title: str
    content: str
    visibility: MedicalRecordVisibility
    created_at: datetime
