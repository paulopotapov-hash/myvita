import uuid
from datetime import datetime

from pydantic import BaseModel

from app.core.schemas import RequestModel
from app.models.waitlist import WaitlistScope, WaitlistStatus


class WaitlistJoin(RequestModel):
    """The patient's own appointment, and whether an earlier slot may be with anyone of the
    same specialty or only with the same professional."""

    appointment_id: uuid.UUID
    scope: WaitlistScope = WaitlistScope.PROFESSIONAL


class WaitlistOfferOut(BaseModel):
    """An earlier slot offered to the patient: names only, never professional ids."""

    id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    staff_name: str
    expires_at: datetime


class WaitlistEntryOut(BaseModel):
    id: uuid.UUID
    appointment_id: uuid.UUID  # the patient's own appointment
    scope: WaitlistScope
    status: WaitlistStatus
    created_at: datetime
    offers: list[WaitlistOfferOut]
