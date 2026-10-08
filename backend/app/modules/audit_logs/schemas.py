import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.audit_log import AuditAction, AuditResult


class AuditActorPublic(BaseModel):
    user_id: uuid.UUID | None
    email: str | None
    # Current display name when the user still exists in this clinic; None for
    # deleted/anonymous actors (the historical email above is kept regardless).
    name: str | None = None


class AuditLogPublic(BaseModel):
    """What a clinic administrator may see. Deliberately omits user_agent and
    the raw row shape; metadata is already allowlisted at write time."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    timestamp: datetime
    actor: AuditActorPublic
    action: AuditAction
    result: AuditResult
    resource_type: str | None
    resource_id: uuid.UUID | None
    ip_address: str | None
    request_id: str | None
    metadata: dict[str, object] | None
