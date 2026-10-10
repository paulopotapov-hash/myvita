import uuid
from datetime import UTC, date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.schemas import RequestModel
from app.models.clinical_result import ClinicalResultCategory, ClinicalResultStatus

_TEXT_FIELDS = ("title", "value", "unit", "reference_range", "summary")


def _strip_or_reject_blank(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        raise ValueError("must not be blank")
    return value


def _not_in_future(value: date | None) -> date | None:
    if value is not None and value > datetime.now(UTC).date():
        raise ValueError("result_date must not be in the future")
    return value


class ClinicalResultContent(RequestModel):
    """Clinical content of a result. Clinic, patient and author come from the URL and the session."""

    model_config = ConfigDict(extra="forbid")

    category: ClinicalResultCategory
    title: str = Field(min_length=1, max_length=200)
    value: str | None = Field(default=None, min_length=1, max_length=200)
    unit: str | None = Field(default=None, min_length=1, max_length=50)
    reference_range: str | None = Field(default=None, min_length=1, max_length=100)
    summary: str | None = Field(default=None, min_length=1, max_length=5000)
    result_date: date
    # Optional link to an existing document of the same patient (e.g. the lab report PDF).
    document_id: uuid.UUID | None = None
    # Make the result available to the patient immediately (otherwise it stays a draft).
    release: bool = False

    strip_text = field_validator(*_TEXT_FIELDS)(_strip_or_reject_blank)
    check_result_date = field_validator("result_date")(_not_in_future)

    @model_validator(mode="after")
    def has_content(self) -> "ClinicalResultContent":
        if self.value is None and self.summary is None and self.document_id is None:
            raise ValueError("A result needs a value, a summary or a linked document.")
        if self.value is None and (self.unit is not None or self.reference_range is not None):
            raise ValueError("unit and reference_range require a value")
        return self

    def content_fields(self) -> dict[str, object]:
        return self.model_dump(include=set(CONTENT_FIELDS))


CONTENT_FIELDS = (
    "category",
    "title",
    "value",
    "unit",
    "reference_range",
    "summary",
    "result_date",
    "document_id",
)
CORRECTION_REASON_MIN_LENGTH = 5
CORRECTION_REASON_MAX_LENGTH = 1000


def _clean_reason(value: str | None) -> str | None:
    """A correction says why, in words: surrounding spaces do not count towards the minimum."""
    if value is None:
        return None
    value = value.strip()
    if len(value) < CORRECTION_REASON_MIN_LENGTH:
        raise ValueError(f"correction_reason needs at least {CORRECTION_REASON_MIN_LENGTH} characters")
    return value


class ClinicalResultCreateRequest(ClinicalResultContent):
    """A new, original result for the patient in the URL."""


class ClinicalResultCorrectionRequest(ClinicalResultContent):
    """The complete corrected result. The patient comes from the result being corrected,
    and the released original is kept unchanged."""

    correction_reason: str = Field(min_length=CORRECTION_REASON_MIN_LENGTH, max_length=CORRECTION_REASON_MAX_LENGTH)

    clean_reason = field_validator("correction_reason")(_clean_reason)


class ClinicalResultUpdateRequest(RequestModel):
    """Only drafts can be edited; a released result is corrected by a new result.

    `correction_reason` may only be edited on a draft correction.
    """

    model_config = ConfigDict(extra="forbid")

    category: ClinicalResultCategory | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    value: str | None = Field(default=None, min_length=1, max_length=200)
    unit: str | None = Field(default=None, min_length=1, max_length=50)
    reference_range: str | None = Field(default=None, min_length=1, max_length=100)
    summary: str | None = Field(default=None, min_length=1, max_length=5000)
    result_date: date | None = None
    document_id: uuid.UUID | None = None
    correction_reason: str | None = Field(
        default=None, min_length=CORRECTION_REASON_MIN_LENGTH, max_length=CORRECTION_REASON_MAX_LENGTH
    )

    strip_text = field_validator(*_TEXT_FIELDS)(_strip_or_reject_blank)
    check_result_date = field_validator("result_date")(_not_in_future)
    clean_reason = field_validator("correction_reason")(_clean_reason)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "ClinicalResultUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("At least one field is required.")
        for name in ("category", "title", "result_date", "correction_reason"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} must not be null")
        return self


class ClinicalResultStaffView(BaseModel):
    """Professional view: includes the draft/released workflow state."""

    view: Literal["staff"] = "staff"
    id: uuid.UUID
    patient_id: uuid.UUID
    category: ClinicalResultCategory
    title: str
    value: str | None
    unit: str | None
    reference_range: str | None
    summary: str | None
    result_date: date
    document_id: uuid.UUID | None
    status: ClinicalResultStatus
    author_name: str
    released_at: datetime | None
    released_by_name: str | None
    # Correction chain: the released result this one corrects (with the reason),
    # and the correction of this result, if any (draft or released).
    corrects_result_id: uuid.UUID | None
    correction_reason: str | None
    corrected_by_result_id: uuid.UUID | None
    # True once a released correction replaces this result for the patient.
    superseded: bool
    created_at: datetime
    updated_at: datetime


class ClinicalResultPatientView(BaseModel):
    """Patient view: released results only, no workflow or internal staff fields.

    Corrections are linked both ways through released results only; a draft
    correction, and the professional's internal correction reason, are never shown.
    """

    view: Literal["patient"] = "patient"
    id: uuid.UUID
    category: ClinicalResultCategory
    title: str
    value: str | None
    unit: str | None
    reference_range: str | None
    summary: str | None
    result_date: date
    document_id: uuid.UUID | None
    author_name: str
    released_at: datetime
    corrects_result_id: uuid.UUID | None
    superseded_by_result_id: uuid.UUID | None


ClinicalResultPublic = Annotated[
    ClinicalResultStaffView | ClinicalResultPatientView, Field(discriminator="view")
]
