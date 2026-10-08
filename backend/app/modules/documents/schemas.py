import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    uploaded_by_user_id: uuid.UUID
    original_filename: str
    content_type: str
    file_size: int
    created_at: datetime


class DocumentPage(BaseModel):
    items: list[DocumentPublic]
    total: int
