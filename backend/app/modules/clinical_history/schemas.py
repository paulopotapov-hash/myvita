import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.schemas import RequestModel
from app.models.clinical_history import (
    AllergySeverity,
    ConditionStatus,
    HistoryCategory,
    HistoryChangeKind,
    HistoryOrigin,
)

# "2010", "2010-03" or "2010-03-12" (decision D5). Checked in the service, which knows the category.
PartialDateText = Annotated[str, Field(min_length=4, max_length=10)]


class _EntryFields(RequestModel):
    """Content fields. Which ones a category accepts and requires is checked by the service
    (and by the database CHECK constraints), so the error names the offending field."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, max_length=200)
    condition_status: ConditionStatus | None = None
    onset: PartialDateText | None = None
    resolved: PartialDateText | None = None
    occurred: PartialDateText | None = None
    location: str | None = Field(default=None, max_length=200)
    reaction: str | None = Field(default=None, max_length=500)
    severity: AllergySeverity | None = None
    note_text: str | None = Field(default=None, max_length=5000)


class ClinicalHistoryCreateRequest(_EntryFields):
    category: HistoryCategory


class ClinicalHistoryUpdateRequest(_EntryFields):
    """Fields present are replaced (null clears an optional field); the category never changes."""

    expected_version: int = Field(ge=1)


class VersionedRequest(RequestModel):
    expected_version: int = Field(ge=1)


class HideRequest(VersionedRequest):
    reason: str = Field(min_length=1, max_length=500)


class DeleteRequest(VersionedRequest):
    # Required when a professional deletes; optional for a patient removing their own declaration.
    reason: str | None = Field(default=None, max_length=500)


class _EntryOut(BaseModel):
    id: uuid.UUID
    category: HistoryCategory
    name: str | None
    condition_status: ConditionStatus | None
    onset: str | None
    resolved: str | None
    occurred: str | None
    location: str | None
    reaction: str | None
    severity: AllergySeverity | None
    note_text: str | None
    origin: HistoryOrigin
    confirmed: bool
    confirmed_at: datetime | None
    confirmed_by_name: str | None
    version: int
    created_at: datetime
    updated_at: datetime


class ClinicalHistoryStaffView(_EntryOut):
    view: Literal["staff"] = "staff"
    created_by_name: str
    hidden: bool
    hidden_at: datetime | None
    hidden_reason: str | None
    hidden_by_name: str | None


class ClinicalHistoryPatientView(_EntryOut):
    """No staff identifiers and nothing about hiding (hidden entries are never sent)."""

    view: Literal["patient"] = "patient"
    can_edit: bool


ClinicalHistoryOut = Annotated[ClinicalHistoryStaffView | ClinicalHistoryPatientView, Field(discriminator="view")]


class ClinicalHistoryRevisionOut(BaseModel):
    version: int
    change_kind: HistoryChangeKind
    changed_by_name: str
    change_reason: str | None
    snapshot: dict[str, Any]
    created_at: datetime
