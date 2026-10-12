import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.core.schemas import RequestModel

# Shown to the patient next to the upload controls (and kept here so the API states them too).
PHOTO_REQUIREMENTS = (
    "A cores.",
    "Com o rosto bem visível.",
    "Sem filtros nem efeitos.",
    "Só tu na fotografia.",
)


class PhotoRef(BaseModel):
    """A photo the caller may display: its image is GET /api/v1/patient-photos/{id}/image."""

    id: uuid.UUID
    created_at: datetime


class PhotoRejection(BaseModel):
    reason: str
    rejected_at: datetime | None


class MyPhotoOut(BaseModel):
    """The patient's own photo state."""

    approved: PhotoRef | None
    pending: PhotoRef | None  # shown to the patient as "Pendente de aprovação"
    rejected: PhotoRejection | None  # until the next upload
    requirements: list[str]


class PatientPhotoStaffOut(BaseModel):
    """Staff view of a patient's photo: the approved one for whoever may open the file; the
    pending one only for the approving doctors."""

    approved: PhotoRef | None
    pending: PhotoRef | None
    can_review: bool


class PendingCount(BaseModel):
    count: int


class PhotoRejectIn(RequestModel):
    reason: str = Field(min_length=1, max_length=300)

    @field_validator("reason")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Indica o motivo.")
        return value
