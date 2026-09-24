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
    model_config = {"from_attributes": True}
