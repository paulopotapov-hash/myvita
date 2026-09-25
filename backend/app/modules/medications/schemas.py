import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.schemas import RequestModel
from app.models.medication import MedicationStatus


class MedicationCreateRequest(RequestModel):
    name: str = Field(min_length=1, max_length=200)
    dosage: str = Field(min_length=1, max_length=200)
    instructions: str | None = Field(default=None, max_length=2000)
    start_date: date
    end_date: date | None = None

    @field_validator("name", "dosage")
    @classmethod
    def non_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @model_validator(mode="after")
    def dates_are_ordered(self) -> "MedicationCreateRequest":
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date must not precede start_date")
        return self


class MedicationUpdateRequest(RequestModel):
    dosage: str | None = Field(default=None, min_length=1, max_length=200)
    instructions: str | None = Field(default=None, max_length=2000)
    status: MedicationStatus | None = None
    end_date: date | None = None

    @field_validator("dosage")
    @classmethod
    def dosage_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @model_validator(mode="after")
    def at_least_one_field(self) -> "MedicationUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("At least one field is required.")
        return self


class MedicationPublic(BaseModel):
    id: uuid.UUID
    clinic_id: uuid.UUID
    patient_id: uuid.UUID
    prescribed_by_staff_id: uuid.UUID
    name: str
    dosage: str
    instructions: str | None
    status: MedicationStatus
    start_date: date
    end_date: date | None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
