import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class RecordCreate(BaseModel):
    patient_id: uuid.UUID
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)


class RecordUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    content: str | None = Field(default=None, min_length=1)


class RecordPublic(RecordCreate):
    id: uuid.UUID
    author_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class MedicationCreate(BaseModel):
    patient_id: uuid.UUID
    name: str = Field(min_length=1, max_length=255)
    dose: str = Field(min_length=1, max_length=100)
    frequency: str = Field(min_length=1, max_length=100)
    start_date: date
    end_date: date | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def dates_ordered(self) -> "MedicationCreate":
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("Data de fim anterior à data de início.")
        return self


class MedicationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    dose: str | None = Field(default=None, min_length=1, max_length=100)
    frequency: str | None = Field(default=None, min_length=1, max_length=100)
    end_date: date | None = None
    notes: str | None = None
    is_active: bool | None = None


class MedicationPublic(MedicationCreate):
    id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class ConsentCreate(BaseModel):
    patient_id: uuid.UUID
    consent_type: str = Field(min_length=1, max_length=100)
    status: Literal["granted", "withdrawn", "declined"]
    version: str = Field(min_length=1, max_length=50)
    effective_at: datetime

    @field_validator("effective_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("A data deve incluir timezone.")
        return value


class ConsentPublic(ConsentCreate):
    id: uuid.UUID
    recorded_by_user_id: uuid.UUID
    created_at: datetime
    model_config = {"from_attributes": True}


class NotificationPublic(BaseModel):
    id: uuid.UUID
    title: str
    message: str
    kind: str
    is_read: bool
    created_at: datetime
    model_config = {"from_attributes": True}
