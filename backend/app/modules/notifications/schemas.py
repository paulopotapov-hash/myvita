import uuid
from datetime import datetime

from pydantic import BaseModel


class NotificationPublic(BaseModel):
    id: uuid.UUID
    title: str
    message: str
    is_read: bool
    read_at: datetime | None
    created_at: datetime
    target_type: str | None
    target_id: uuid.UUID | None
    conversation_target_id: uuid.UUID | None = None
    model_config = {"from_attributes": True}
