import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.schemas import RequestModel
from app.models.conversation import ConversationStatus

MESSAGE_MAX_LENGTH = 5_000


class ConversationCreateRequest(RequestModel):
    """
    Only clinical staff open conversations, with a patient they are currently
    assigned to. The professional side is always derived from the session,
    never from the body. Patients cannot start conversations.
    """

    patient_id: uuid.UUID


class MessageCreateRequest(RequestModel):
    body: str = Field(min_length=1, max_length=MESSAGE_MAX_LENGTH)

    @field_validator("body")
    @classmethod
    def non_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class ConversationStatusRequest(RequestModel):
    """Nurses triage the non-closed states; only a doctor closes or reopens."""

    status: ConversationStatus


# Who wrote a message, for display. Never an internal user id.
SenderRole = Literal["patient", "doctor", "nurse", "staff"]


class MessagePublic(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    sender_name: str
    sender_role: SenderRole
    # True when the caller wrote it (replaces exposing the sender's user id).
    is_mine: bool
    body: str
    read_at: datetime | None
    created_at: datetime


class ConversationTeamState(BaseModel):
    """Care-team workflow details. Staff only: patients never receive triage metadata."""

    needs_doctor_review: bool
    escalated_at: datetime | None
    escalated_by_name: str | None
    closed_by_name: str | None


class ConversationPublic(BaseModel):
    id: uuid.UUID
    # Internal identifiers for staff workflows; null for patients (who are shown names only).
    clinic_id: uuid.UUID | None
    patient_id: uuid.UUID | None
    staff_id: uuid.UUID | None
    patient_name: str
    # The professional who opened the thread; the whole active care team takes part.
    staff_name: str
    status: ConversationStatus
    closed_at: datetime | None
    # Patient: messages from the team not read yet. Staff: patient messages that
    # no team member has opened yet (a shared team flag).
    unread_count: int
    # False when the conversation is closed, when the caller may not reply, or
    # (for the patient) when nobody on the care team could read a reply.
    can_reply: bool
    team: ConversationTeamState | None = None
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationPublic):
    # Newest first, one page at a time — see the `page`/`page_size` query
    # parameters and the X-Total-Count header on GET /conversations/{id}.
    messages: list[MessagePublic]


class MarkReadResponse(BaseModel):
    updated_count: int
