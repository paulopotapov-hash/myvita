import uuid

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.audit import audit_denials, record_access
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import AuditAction, ClinicalConversation, ClinicalMessage, User
from app.modules.messaging.schemas import (
    ConversationCreate,
    ConversationDetail,
    ConversationListItem,
    ConversationStatusUpdate,
    MessageCreate,
    MessagePublic,
)
from app.modules.messaging.service import (
    create_conversation,
    escalate_to_doctor,
    get_conversation,
    list_conversations,
    send_message,
    update_status,
)

router = APIRouter()


def _audit(
    request: Request,
    user: User,
    action: AuditAction,
    conversation_id: uuid.UUID,
    *,
    metadata: dict[str, object] | None = None,
) -> None:
    record_access(request, user, action, "conversation", conversation_id, metadata=metadata)


def _message_public(message: ClinicalMessage) -> MessagePublic:
    return MessagePublic.model_validate(message)


def _list_public(conversation: ClinicalConversation, user: User) -> ConversationListItem:
    last_message = conversation.messages[-1]
    return ConversationListItem(
        id=conversation.id,
        patient_id=conversation.patient_id,
        patient_name=conversation.patient.user.full_name,
        subject=conversation.subject,
        status=conversation.status,
        needs_doctor_review=conversation.needs_doctor_review,
        updated_at=conversation.updated_at,
        closed_at=conversation.closed_at,
        last_message=_message_public(last_message),
        unread=conversation.patient_unread if user.role.value == "patient" else conversation.team_unread,
    )


def _detail_public(conversation: ClinicalConversation, user: User) -> ConversationDetail:
    item = _list_public(conversation, user)
    return ConversationDetail(
        **item.model_dump(exclude={"unread"}),
        unread=item.unread,
        messages=[_message_public(message) for message in conversation.messages],
    )


@router.get("/inbox", response_model=list[ConversationListItem])
def inbox(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ConversationListItem]:
    with audit_denials(request, user, "conversation", user.id):
        conversations = list_conversations(db, user)
    response.headers["X-Total-Count"] = str(len(conversations))
    for conversation in conversations:
        _audit(request, user, AuditAction.CONVERSATION_VIEWED, conversation.id)
    return [_list_public(item, user) for item in conversations]


@router.post(
    "/patients/{patient_id}/conversations", response_model=ConversationDetail, status_code=201
)
def start_conversation(
    patient_id: uuid.UUID,
    payload: ConversationCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ConversationDetail:
    with audit_denials(request, user, "patient", patient_id):
        conversation = create_conversation(db, patient_id, payload, user)
    _audit(request, user, AuditAction.CONVERSATION_CREATED, conversation.id)
    _audit(request, user, AuditAction.MESSAGE_SENT, conversation.id, metadata={"initial_message": True})
    return _detail_public(conversation, user)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def detail(
    conversation_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ConversationDetail:
    with audit_denials(request, user, "conversation", conversation_id):
        conversation = get_conversation(db, conversation_id, user)
    _audit(request, user, AuditAction.CONVERSATION_VIEWED, conversation.id)
    return _detail_public(conversation, user)


@router.post("/conversations/{conversation_id}/messages", response_model=ConversationDetail)
def reply(
    conversation_id: uuid.UUID,
    payload: MessageCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ConversationDetail:
    with audit_denials(request, user, "conversation", conversation_id):
        conversation, escalation_cleared = send_message(db, conversation_id, payload, user)
    _audit(request, user, AuditAction.MESSAGE_SENT, conversation.id)
    if escalation_cleared:
        _audit(request, user, AuditAction.CONVERSATION_ESCALATION_CLEARED, conversation.id)
    return _detail_public(conversation, user)


@router.patch("/conversations/{conversation_id}/status", response_model=ConversationDetail)
def change_status(
    conversation_id: uuid.UUID,
    payload: ConversationStatusUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ConversationDetail:
    with audit_denials(request, user, "conversation", conversation_id):
        conversation, changed, previous = update_status(db, conversation_id, payload, user)
    if changed:
        _audit(
            request,
            user,
            AuditAction.CONVERSATION_STATUS_CHANGED,
            conversation.id,
            metadata={"from": previous.value, "to": conversation.status.value},
        )
    return _detail_public(conversation, user)


@router.post("/conversations/{conversation_id}/escalation", response_model=ConversationDetail)
def escalate(
    conversation_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ConversationDetail:
    with audit_denials(request, user, "conversation", conversation_id):
        conversation, changed = escalate_to_doctor(db, conversation_id, user)
    if changed:
        _audit(request, user, AuditAction.CONVERSATION_ESCALATED, conversation.id)
    return _detail_public(conversation, user)
