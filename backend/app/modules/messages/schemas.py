import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.core.schemas import RequestModel

MESSAGE_MAX_LENGTH = 5_000


class ConversationCreateRequest(RequestModel):
    """
    The counterpart depends on who is asking: clinical staff send
    `patient_id`, patients send `staff_id`. The caller's own side is always
    derived from the session, never from the body.
    """

    patient_id: uuid.UUID | None = None
    staff_id: uuid.UUID | None = None


class MessageCreateRequest(RequestModel):
    body: str = Field(min_length=1, max_length=MESSAGE_MAX_LENGTH)

    @field_validator("body")
    @classmethod
    def non_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class MessagePublic(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    sender_user_id: uuid.UUID
    body: str
    read_at: datetime | None
    created_at: datetime
    model_config = {"from_attributes": True}


class ConversationPublic(BaseModel):
    id: uuid.UUID
    clinic_id: uuid.UUID
    patient_id: uuid.UUID
    staff_id: uuid.UUID
    patient_name: str
    staff_name: str
    # Messages addressed to the current user that they haven't read yet.
    unread_count: int
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationPublic):
    # Newest first, one page at a time — see the `page`/`page_size` query
    # parameters and the X-Total-Count header on GET /conversations/{id}.
    messages: list[MessagePublic]


class MarkReadResponse(BaseModel):
    updated_count: int
