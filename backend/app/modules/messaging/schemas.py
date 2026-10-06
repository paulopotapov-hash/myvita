import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.core.schemas import RequestModel
from app.models.conversation import ConversationStatus, MessageSenderRole


class ConversationCreate(RequestModel):
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=10000)

    @field_validator("subject", "body")
    @classmethod
    def nonblank_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("O texto não pode estar vazio.")
        return value


class MessageCreate(RequestModel):
    body: str = Field(min_length=1, max_length=10000)

    @field_validator("body")
    @classmethod
    def nonblank_body(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("A mensagem não pode estar vazia.")
        return value


class ConversationStatusUpdate(RequestModel):
    status: ConversationStatus


class MessagePublic(BaseModel):
    id: uuid.UUID
    sender_name: str
    sender_role: MessageSenderRole
    body: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationListItem(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    patient_name: str
    subject: str
    status: ConversationStatus
    needs_doctor_review: bool
    updated_at: datetime
    closed_at: datetime | None
    last_message: MessagePublic
    unread: bool


class ConversationDetail(ConversationListItem):
    messages: list[MessagePublic]
