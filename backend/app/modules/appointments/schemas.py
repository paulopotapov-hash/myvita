import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.appointment import AppointmentStatus


class AppointmentCreateRequest(BaseModel):
    """
    Created by staff/clinic_admin. clinic_id is deliberately NOT part of
    this payload — it's always taken from the authenticated staff member's
    own session (see core/security.get_current_clinic_id), never trusted
    from the client, so a request can't be aimed at another clinic.
    """
    patient_id: uuid.UUID
    staff_id: uuid.UUID
    scheduled_at: datetime
    duration_minutes: int = Field(default=30, ge=5, le=480)
    reason: str | None = Field(default=None, max_length=500)


class AppointmentPublic(BaseModel):
    id: uuid.UUID
    clinic_id: uuid.UUID
    patient_id: uuid.UUID
    staff_id: uuid.UUID
    scheduled_at: datetime
    duration_minutes: int
    status: AppointmentStatus
    reason: str | None

    model_config = {"from_attributes": True}
