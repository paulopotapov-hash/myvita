import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.core.schemas import RequestModel


class MedicalRecordCreateRequest(RequestModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=20_000)

    @field_validator("title", "content")
    @classmethod
    def non_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class MedicalRecordUpdateRequest(MedicalRecordCreateRequest):
    pass


class MedicalRecordPublic(BaseModel):
    id: uuid.UUID
    clinic_id: uuid.UUID
    patient_id: uuid.UUID
    author_staff_id: uuid.UUID
    title: str
    content: str
    version: int
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class MedicalRecordRevisionPublic(BaseModel):
    id: uuid.UUID
    record_id: uuid.UUID
    editor_staff_id: uuid.UUID
    version: int
    title: str
    content: str
    created_at: datetime
    model_config = {"from_attributes": True}
