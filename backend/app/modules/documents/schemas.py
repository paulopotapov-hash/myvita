import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

DOCUMENT_TITLE_MAX_LENGTH = 200


class DocumentPublic(BaseModel):
    """Document metadata shown to staff and to the patient.

    The uploader is exposed by display name only, never by internal user id.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    title: str
    uploaded_by_name: str
    original_filename: str
    content_type: str
    file_size: int
    created_at: datetime


class DocumentPage(BaseModel):
    items: list[DocumentPublic]
    total: int
