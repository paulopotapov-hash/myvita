import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.schemas import RequestModel
from app.models.consent import ConsentStatus, ConsentType


class ConsentCreateRequest(RequestModel):
    """Consent status, clinic and actor are derived by the server."""

    consent_type: ConsentType
    purpose: str = Field(min_length=1, max_length=500)
    policy_version: str | None = Field(default=None, min_length=1, max_length=100)
    policy_text: str | None = Field(default=None, min_length=1, max_length=20_000)

    @field_validator("purpose")
    @classmethod
    def purpose_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("purpose must not be empty")
        return value

    @field_validator("policy_version", "policy_text")
    @classmethod
    def optional_policy_fields_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @model_validator(mode="after")
    def policy_snapshot_is_complete_when_present(self) -> "ConsentCreateRequest":
        if (self.policy_version is None) != (self.policy_text is None):
            raise ValueError("policy_version and policy_text must be supplied together")
        return self


class ConsentPublic(BaseModel):
    id: uuid.UUID
    clinic_id: uuid.UUID
    patient_id: uuid.UUID
    consent_type: ConsentType
    purpose: str
    policy_version: str | None
    policy_text: str | None
    status: ConsentStatus
    granted_at: datetime
    revoked_at: datetime | None
    recorded_by_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
