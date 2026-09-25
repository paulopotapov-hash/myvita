import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.core.schemas import RequestModel
from app.models.consent import ConsentStatus, ConsentType


class ConsentCreateRequest(RequestModel):
    """Consent status, clinic and actor are derived by the server."""

    consent_type: ConsentType
    purpose: str = Field(min_length=1, max_length=500)

    @field_validator("purpose")
    @classmethod
    def purpose_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("purpose must not be empty")
        return value


class ConsentPublic(BaseModel):
    id: uuid.UUID
    clinic_id: uuid.UUID
    patient_id: uuid.UUID
    consent_type: ConsentType
    purpose: str
    status: ConsentStatus
    granted_at: datetime
    revoked_at: datetime | None
    recorded_by_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
