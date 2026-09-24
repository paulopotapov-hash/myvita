import uuid
from datetime import date, datetime

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


class MedicationPayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid", populate_by_name=True)


class MedicationCreate(MedicationPayload):
    name: str = Field(min_length=1, max_length=255)
    dosage: str = Field(
        min_length=1,
        max_length=100,
        validation_alias=AliasChoices("dosage", "dose"),
    )
    route: str | None = Field(default=None, min_length=1, max_length=100)
    frequency: str = Field(min_length=1, max_length=100)
    instructions: str | None = Field(
        default=None,
        min_length=1,
        max_length=5_000,
        validation_alias=AliasChoices("instructions", "notes"),
    )
    start_date: date
    end_date: date | None = None

    @model_validator(mode="after")
    def dates_ordered(self) -> "MedicationCreate":
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("Data de fim anterior à data de início.")
        return self


class MedicationCreateLegacy(MedicationCreate):
    patient_id: uuid.UUID


class MedicationUpdate(MedicationPayload):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    dosage: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        validation_alias=AliasChoices("dosage", "dose"),
    )
    route: str | None = Field(default=None, min_length=1, max_length=100)
    frequency: str | None = Field(default=None, min_length=1, max_length=100)
    instructions: str | None = Field(
        default=None,
        min_length=1,
        max_length=5_000,
        validation_alias=AliasChoices("instructions", "notes"),
    )
    start_date: date | None = None
    end_date: date | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def not_empty(self) -> "MedicationUpdate":
        if not self.model_fields_set:
            raise ValueError("O pedido de atualização não pode estar vazio.")
        required = {"name", "dosage", "frequency", "start_date", "is_active"}
        if any(getattr(self, field) is None for field in required & self.model_fields_set):
            raise ValueError("Campo obrigatório não pode ser nulo.")
        return self


class MedicationStop(MedicationPayload):
    end_date: date | None = None


class MedicationPublic(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    name: str
    dosage: str
    route: str | None
    frequency: str
    instructions: str | None
    start_date: date
    end_date: date | None
    is_active: bool
    created_by_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
