import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.schemas import RequestModel
from app.models.clinical_history import HistoryOrigin
from app.models.medication import MedicationStatus

PartialDateText = Annotated[str, Field(min_length=4, max_length=10)]


class MedicationCreateRequest(RequestModel):
    """A professional's prescription (dose required) or a patient's declaration (dose optional, D6)."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    dosage: str | None = Field(default=None, min_length=1, max_length=200)
    route: str | None = Field(default=None, min_length=1, max_length=100)
    frequency: str | None = Field(default=None, min_length=1, max_length=100)
    instructions: str | None = Field(default=None, min_length=1, max_length=2000)
    # "2020", "2020-03" or "2020-03-12". A professional must give the complete date; in a
    # patient's declaration it is optional and may be partial (checked by the service).
    start_date: PartialDateText | None = None
    end_date: date | None = None

    @field_validator("name", "dosage")
    @classmethod
    def non_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value



class MedicationUpdateRequest(RequestModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    dosage: str | None = Field(default=None, min_length=1, max_length=200)
    route: str | None = Field(default=None, min_length=1, max_length=100)
    frequency: str | None = Field(default=None, min_length=1, max_length=100)
    instructions: str | None = Field(default=None, min_length=1, max_length=2000)
    status: MedicationStatus | None = None
    # Null (clearing it) is only accepted from the patient, for their own declaration.
    start_date: PartialDateText | None = None
    end_date: date | None = None

    @field_validator("name", "dosage", "route", "frequency")
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
        for name in ("name", "dosage", "status"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} must not be null")
        return self


class MedicationConfirmRequest(RequestModel):
    """Confirming a patient's declaration; the professional may complete the dose (D6)."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    dosage: str | None = Field(default=None, min_length=1, max_length=200)
    # The professional may complete a partial or missing start date with the full date.
    start_date: date | None = None


class MedicationHideRequest(RequestModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    reason: str = Field(min_length=1, max_length=500)


class MedicationDeleteRequest(RequestModel):
    """Soft delete. Required reason for a professional; optional for a patient's own declaration."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    reason: str | None = Field(default=None, max_length=500)


class MedicationDeactivateRequest(RequestModel):
    model_config = ConfigDict(extra="forbid")

    end_date: date | None = None


class MedicationPublic(BaseModel):
    """Professional view (care team): includes the internal identifiers staff workflows use."""

    view: Literal["staff"] = "staff"
    id: uuid.UUID
    clinic_id: uuid.UUID
    patient_id: uuid.UUID
    prescribed_by_staff_id: uuid.UUID | None
    name: str
    dosage: str | None
    route: str | None
    frequency: str | None
    instructions: str | None
    status: MedicationStatus
    start_date: str | None  # "2020", "2020-03" or "2020-03-12"
    end_date: date | None
    # Clinical history (commit 3): origin, confirmation and hiding from the patient (D4).
    origin: HistoryOrigin
    confirmed: bool
    confirmed_at: datetime | None
    confirmed_by_staff_id: uuid.UUID | None
    hidden: bool
    hidden_at: datetime | None
    hidden_reason: str | None
    created_at: datetime
    updated_at: datetime


class MedicationPatientView(BaseModel):
    """Patient view: what the patient needs to understand and take the medication.

    Built field by field (never from the ORM row), so internal identifiers such as
    clinic_id, patient_id or prescribed_by_staff_id cannot leak through it.
    """

    view: Literal["patient"] = "patient"
    id: uuid.UUID
    name: str
    dosage: str | None
    route: str | None
    frequency: str | None
    instructions: str | None
    status: MedicationStatus
    start_date: str | None  # "2020", "2020-03" or "2020-03-12"
    end_date: date | None
    origin: HistoryOrigin
    confirmed: bool
    # The patient's own declaration, not yet confirmed (D3).
    can_edit: bool
    created_at: datetime
    updated_at: datetime


MedicationOut = Annotated[MedicationPublic | MedicationPatientView, Field(discriminator="view")]
