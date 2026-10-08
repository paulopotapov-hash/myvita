import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core.audit import audit_request
from app.core.database import get_db
from app.core.rate_limit import AUTHENTICATED_WRITE_RATE_LIMIT, limiter
from app.core.security import get_current_user
from app.models import AuditAction, Message, User
from app.modules.messages.schemas import (
    ConversationCreateRequest,
    ConversationDetail,
    ConversationPublic,
    MarkReadResponse,
    MessageCreateRequest,
    MessagePublic,
)
from app.modules.messages.service import (
    create_conversation,
    get_conversation_detail,
    list_conversations,
    mark_conversation_read,
    send_message,
)

router = APIRouter()

_NOT_FOUND_RESPONSE: dict[int | str, dict[str, Any]] = {
    404: {
        "description": "Conversation does not exist, belongs to another clinic, or the caller is not a participant."
    }
}


def _audit(
    request: Request,
    user: User,
    action: AuditAction,
    resource_type: str,
    resource_id: uuid.UUID,
    metadata: dict[str, object] | None = None,
) -> None:
    # Identifiers only — message bodies never go into the audit trail.
    audit_request(
        request,
        action=action,
        actor=user,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata=metadata,
    )


@router.post(
    "",
    response_model=ConversationPublic,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {
            "description": "A conversation with this participant already exists and is returned.",
            "model": ConversationPublic,
        },
        403: {
            "description": "Caller is not clinical staff or a patient, or a patient has no appointment with that professional."
        },
        404: {"description": "Patient/professional not found in the caller's clinic."},
        422: {"description": "Wrong counterpart field for the caller's role."},
    },
)
@limiter.limit(AUTHENTICATED_WRITE_RATE_LIMIT)
def create(
    payload: ConversationCreateRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ConversationPublic:
    """Start (or reopen) a patient <-> clinical staff conversation.

    Clinical staff (doctor/nurse) send `patient_id` of a patient in their
    clinic. Patients send `staff_id` of a doctor/nurse they have an
    appointment with. Clinic admins cannot start conversations.
    """
    conversation, created = create_conversation(db, payload, user)
    if created:
        _audit(request, user, AuditAction.CONVERSATION_CREATED, "conversation", conversation.id)
    else:
        response.status_code = status.HTTP_200_OK
    return conversation


@router.get("", response_model=list[ConversationPublic])
def list_mine(
    response: Response,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ConversationPublic]:
    """Conversations the caller participates in, most recently active first. Total in `X-Total-Count`."""
    conversations, total = list_conversations(db, user, offset=(page - 1) * page_size, limit=page_size)
    response.headers["X-Total-Count"] = str(total)
    return conversations


@router.get("/{conversation_id}", response_model=ConversationDetail, responses=_NOT_FOUND_RESPONSE)
def detail(
    conversation_id: uuid.UUID,
    request: Request,
    response: Response,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ConversationDetail:
    """One conversation with a page of its messages (newest first). Message total in `X-Total-Count`.

    Viewing does not mark messages as read — use `POST /{conversation_id}/read`.
    """
    conversation, total = get_conversation_detail(
        db, conversation_id, user, offset=(page - 1) * page_size, limit=page_size
    )
    response.headers["X-Total-Count"] = str(total)
    _audit(request, user, AuditAction.CONVERSATION_VIEWED, "conversation", conversation.id)
    return conversation


@router.post(
    "/{conversation_id}/messages",
    response_model=MessagePublic,
    status_code=status.HTTP_201_CREATED,
    responses={
        **_NOT_FOUND_RESPONSE,
        422: {"description": "Body is empty, whitespace-only or longer than 5000 characters."},
    },
)
@limiter.limit(AUTHENTICATED_WRITE_RATE_LIMIT)
def send(
    conversation_id: uuid.UUID,
    payload: MessageCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Message:
    """Send a plain-text message. The other participant gets a generic notification (no content)."""
    message = send_message(db, conversation_id, payload.body, user)
    _audit(
        request,
        user,
        AuditAction.MESSAGE_SENT,
        "message",
        message.id,
        metadata={"conversation_id": str(message.conversation_id)},
    )
    return message


@router.post("/{conversation_id}/read", response_model=MarkReadResponse, responses=_NOT_FOUND_RESPONSE)
def mark_read(
    conversation_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MarkReadResponse:
    """Mark every unread message the caller *received* in this conversation as read.

    Messages the caller sent are never modified. Idempotent: returns 0 when nothing was unread.
    """
    updated_count = mark_conversation_read(db, conversation_id, user)
    _audit(
        request,
        user,
        AuditAction.MESSAGE_READ,
        "conversation",
        conversation_id,
        metadata={"updated_count": updated_count},
    )
    return MarkReadResponse(updated_count=updated_count)
