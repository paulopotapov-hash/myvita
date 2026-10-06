import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.core.schemas import RequestModel
from app.models import DocumentKind


class DocumentNoteCreate(RequestModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=20_000)

    @field_validator("title", "content")
    @classmethod
    def non_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class DocumentPublic(BaseModel):
    id: uuid.UUID
    clinic_id: uuid.UUID
    patient_id: uuid.UUID
    kind: DocumentKind
    title: str
    current_version: int
    created_at: datetime
    updated_at: datetime
    current_content: str | None = None
    current_author: str | None = None
    model_config = {"from_attributes": True}


class DocumentVersionPublic(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    author_name: str
    version: int
    content: str | None
    original_filename: str | None
    media_type: str | None
    file_size: int | None
    created_at: datetime
    is_current: bool
