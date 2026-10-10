import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core.audit import audit_denials, audit_request
from app.core.clinical_access import staff_profile
from app.core.database import get_db
from app.core.rate_limit import AUTHENTICATED_WRITE_RATE_LIMIT, limiter
from app.core.security import get_current_user
from app.models import AuditAction, ConversationStatus, StaffRole, User, UserRole
from app.modules.messages.schemas import (
    ConversationCreateRequest,
    ConversationDetail,
    ConversationPublic,
    ConversationStatusRequest,
    MarkReadResponse,
    MessageCreateRequest,
    MessagePublic,
    SenderRole,
)
from app.modules.messages.service import (
    change_status,
    create_conversation,
    escalate,
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
            "description": "Caller is a patient, lacks the messaging permission, or has no active care assignment to the patient."
        },
        404: {"description": "Patient not found in the caller's clinic."},
        422: {"description": "Missing or malformed patient_id."},
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
    """Start (or reopen) a conversation with a patient.

    Only clinical staff with the messaging permission and an active care
    assignment to that patient. Patients and clinic admins cannot start
    conversations; patients reply in threads opened by staff.
    """
    with audit_denials(request, user, "patient", payload.patient_id):
        result = create_conversation(db, payload, user)
    conversation = result.conversation
    if result.created:
        _audit(request, user, AuditAction.CONVERSATION_CREATED, "conversation", conversation.id)
    else:
        response.status_code = status.HTTP_200_OK
    if result.reopened_from is not None:
        _audit(
            request,
            user,
            AuditAction.CONVERSATION_STATUS_CHANGED,
            "conversation",
            conversation.id,
            metadata={"from": result.reopened_from.value, "to": conversation.status.value, "operation": "start"},
        )
    return conversation


@router.get("", response_model=list[ConversationPublic])
def list_mine(
    request: Request,
    response: Response,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    status_filter: ConversationStatus | None = Query(default=None, alias="status"),
    needs_review: bool | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ConversationPublic]:
    """Conversations visible to the caller, most recently active first. Total in `X-Total-Count`.

    Professionals see the team inbox: every thread of the patients they are
    currently assigned to. `needs_review` filters on pending doctor review (staff only).
    """
    with audit_denials(request, user, "conversation", user.id):
        conversations, total = list_conversations(
            db,
            user,
            offset=(page - 1) * page_size,
            limit=page_size,
            status_filter=status_filter,
            needs_review=needs_review,
        )
    response.headers["X-Total-Count"] = str(total)
    # Parent A pattern: listing is a read of each conversation shown.
    for conversation in conversations:
        _audit(
            request,
            user,
            AuditAction.CONVERSATION_VIEWED,
            "conversation",
            conversation.id,
            metadata={"operation": "list"},
        )
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
    with audit_denials(request, user, "conversation", conversation_id):
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
) -> MessagePublic:
    """Send a plain-text message. The other side gets a generic notification (no content)
    linking to the conversation: the patient for team messages, the active care team for
    patient messages. 403 when the thread is closed or read-only."""
    with audit_denials(request, user, "conversation", conversation_id):
        result = send_message(db, conversation_id, payload.body, user)
    message = result.message
    _audit(
        request,
        user,
        AuditAction.MESSAGE_SENT,
        "message",
        message.id,
        metadata={"conversation_id": str(message.conversation_id)},
    )
    if result.escalation_cleared:
        _audit(
            request,
            user,
            AuditAction.CONVERSATION_ESCALATION_CLEARED,
            "conversation",
            message.conversation_id,
            metadata={"operation": "doctor_reply"},
        )
    return MessagePublic(
        id=message.id,
        conversation_id=message.conversation_id,
        sender_name=user.full_name,
        sender_role=_own_role(db, user),
        is_mine=True,
        body=message.body,
        read_at=message.read_at,
        created_at=message.created_at,
    )


def _own_role(db: Session, user: User) -> SenderRole:
    if user.role == UserRole.PATIENT:
        return "patient"
    staff = staff_profile(db, user)
    if staff is not None and staff.staff_role == StaffRole.DOCTOR:
        return "doctor"
    if staff is not None and staff.staff_role == StaffRole.NURSE:
        return "nurse"
    return "staff"


@router.post(
    "/{conversation_id}/status",
    response_model=ConversationPublic,
    responses={
        **_NOT_FOUND_RESPONSE,
        403: {"description": "Nurses cannot close or reopen; only doctors can."},
    },
)
@limiter.limit(AUTHENTICATED_WRITE_RATE_LIMIT)
def set_status(
    conversation_id: uuid.UUID,
    payload: ConversationStatusRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ConversationPublic:
    """Triage (nurse: open/waiting states) or close/reopen (doctor). Closing notifies the
    patient generically and makes the conversation read-only. Same status: no change."""
    with audit_denials(request, user, "conversation", conversation_id):
        conversation, previous = change_status(db, conversation_id, payload.status, user)
    if previous is not None:
        _audit(
            request,
            user,
            AuditAction.CONVERSATION_STATUS_CHANGED,
            "conversation",
            conversation_id,
            metadata={"from": previous.value, "to": conversation.status.value},
        )
    return conversation


@router.post(
    "/{conversation_id}/escalate",
    response_model=ConversationPublic,
    responses={
        **_NOT_FOUND_RESPONSE,
        403: {"description": "Only nurses request a doctor's review."},
        409: {"description": "The conversation is closed."},
    },
)
@limiter.limit(AUTHENTICATED_WRITE_RATE_LIMIT)
def request_doctor_review(
    conversation_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ConversationPublic:
    """A nurse flags the conversation for the care team's doctors, who get a generic
    notification. A doctor's reply clears the flag. Repeating it while pending changes nothing."""
    with audit_denials(request, user, "conversation", conversation_id):
        conversation, changed = escalate(db, conversation_id, user)
    if changed:
        _audit(request, user, AuditAction.CONVERSATION_ESCALATED, "conversation", conversation_id)
    return conversation


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
    with audit_denials(request, user, "conversation", conversation_id):
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
