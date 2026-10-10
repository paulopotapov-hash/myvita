"""
Patient <-> care-team clinical messaging (docs/clinical-messaging.md).

A conversation belongs to one patient and is opened by one clinical staff
member; the patient's whole ACTIVE care team (doctors and nurses) shares it in
a team inbox.

Access rule, applied to every list, read and write (re-evaluated per request):
- the conversation belongs to the caller's clinic, and
- the caller is its patient, or a doctor/nurse with the messaging permission
  and a current, active ClinicalCareAssignment for that patient.
Anyone else (ended assignment, other patient, other clinic) gets the same 404
as for an unknown conversation, so IDs can't be probed. Clinic admins and
non-clinical staff are never participants.

Lifecycle: OPEN -> WAITING_FOR_TEAM (patient wrote) / WAITING_FOR_PATIENT
(team wrote) -> CLOSED. Nurses triage the non-closed states and can request a
doctor's review (escalation); a doctor's reply clears that request. Only a
doctor closes or reopens. A closed conversation is read-only for everyone.

The patient can reply only while the conversation is not closed and someone on
the care team could read the reply (at least one active, assigned clinician).
Only clinical staff with the messaging permission and an active assignment
start conversations; patients reply in threads opened by staff.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import and_, false, func, literal, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from app.core.clinical_access import ClinicalAction, clinical_access, has_role_action, staff_profile
from app.models import (
    ClinicalCareAssignment,
    Conversation,
    ConversationStatus,
    Message,
    Patient,
    Staff,
    StaffRole,
    User,
    UserRole,
)
from app.modules.messages.schemas import (
    ConversationCreateRequest,
    ConversationDetail,
    ConversationPublic,
    ConversationTeamState,
    MessagePublic,
    SenderRole,
)
from app.modules.notifications.events import (
    TEMPLATES,
    NotificationEvent,
    NotificationTarget,
    TargetType,
    notify,
)

_NOT_FOUND = "Conversa não encontrada."
INACTIVE_CONVERSATION = "Esta conversa já não está activa. Para continuar, contacte a clínica."
CLOSED_CONVERSATION = "Esta conversa foi encerrada pela equipa clínica."
_PATIENTS_CANNOT_START = "Os pacientes não podem iniciar conversas."
_NO_MESSAGING = "Sem permissões para mensagens."
_NOT_ALLOWED_STATUS = "Não tem permissão para esta alteração de estado."
_ONLY_NURSES_ESCALATE = "Só a equipa de enfermagem pode pedir revisão médica."

# Roles whose professionals take part in conversations (doctor/nurse today).
_REPLY_ROLES = tuple(role for role in StaffRole if has_role_action(role, ClinicalAction.REPLY_CONVERSATIONS))
_DOCTOR_ROLES = tuple(role for role in StaffRole if has_role_action(role, ClinicalAction.MANAGE_CONVERSATIONS))
_TRIAGE_STATUSES = frozenset(
    {ConversationStatus.OPEN, ConversationStatus.WAITING_FOR_PATIENT, ConversationStatus.WAITING_FOR_TEAM}
)

# Deliberately generic: notifications may be seen on shared screens and are
# stored outside the conversation's access rules, so no message content or
# sender name goes into them.
NEW_MESSAGE_NOTIFICATION_TITLE, NEW_MESSAGE_NOTIFICATION_MESSAGE = TEMPLATES[NotificationEvent.MESSAGE_RECEIVED]


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)


@dataclass(frozen=True)
class Caller:
    side: str  # "patient" or "staff"
    staff: Staff | None = None


def _caller(db: Session, user: User) -> Caller | None:
    if user.role == UserRole.PATIENT:
        return Caller("patient")
    staff = staff_profile(db, user)
    if staff is not None and has_role_action(staff.staff_role, ClinicalAction.VIEW_CONVERSATIONS):
        return Caller("staff", staff)
    return None


def _active_assignment(staff_id: Any) -> Any:
    """Correlated EXISTS: `staff_id` is on the conversation's patient's active care team."""
    return (
        select(ClinicalCareAssignment.id)
        .where(
            ClinicalCareAssignment.clinic_id == Conversation.clinic_id,
            ClinicalCareAssignment.patient_id == Conversation.patient_id,
            ClinicalCareAssignment.staff_id == staff_id,
            ClinicalCareAssignment.active.is_(True),
        )
        .correlate(Conversation)
        .exists()
    )


def _team_can_read() -> Any:
    """Correlated EXISTS: at least one active, assigned doctor/nurse could read a patient reply."""
    team_staff = aliased(Staff)
    team_user = aliased(User)
    return (
        select(ClinicalCareAssignment.id)
        .join(team_staff, team_staff.id == ClinicalCareAssignment.staff_id)
        .join(team_user, team_user.id == team_staff.user_id)
        .where(
            ClinicalCareAssignment.clinic_id == Conversation.clinic_id,
            ClinicalCareAssignment.patient_id == Conversation.patient_id,
            ClinicalCareAssignment.active.is_(True),
            team_staff.staff_role.in_(_REPLY_ROLES),
            team_user.is_active.is_(True),
        )
        .correlate(Conversation)
        .exists()
    )


def _summary_query(db: Session, user: User, caller: Caller | None) -> Any:
    """Conversations visible to the caller, with names, unread count and reply state, in one query."""
    patient_user = aliased(User)
    opener_user = aliased(User)
    not_closed = Conversation.status != ConversationStatus.CLOSED
    if caller is not None and caller.side == "patient":
        # Messages from the team the patient has not read.
        unread_filter = Message.sender_user_id != user.id
        can_reply = and_(not_closed, _team_can_read())
    else:
        # Patient messages no one on the team has opened yet (shared flag).
        unread_filter = Message.sender_user_id == patient_user.id
        allowed = caller is not None and caller.staff is not None and caller.staff.staff_role in _REPLY_ROLES
        can_reply = and_(not_closed, literal(allowed))
    unread = (
        select(func.count(Message.id))
        .where(Message.conversation_id == Conversation.id, unread_filter, Message.read_at.is_(None))
        .correlate(Conversation, patient_user)
        .scalar_subquery()
    )
    query = (
        db.query(
            Conversation,
            patient_user.full_name.label("patient_name"),
            opener_user.full_name.label("staff_name"),
            unread.label("unread_count"),
            can_reply.label("can_reply"),
        )
        .join(Patient, Patient.id == Conversation.patient_id)
        .join(patient_user, patient_user.id == Patient.user_id)
        .join(Staff, Staff.id == Conversation.staff_id)
        .join(opener_user, opener_user.id == Staff.user_id)
        .filter(Conversation.clinic_id == user.clinic_id)
    )
    if caller is None:
        return query.filter(false())
    if caller.side == "patient":
        # The patient always keeps their history; `can_reply` makes closed/unattended threads read-only.
        return query.filter(Patient.user_id == user.id)
    assert caller.staff is not None
    # Team inbox: every thread of a patient the caller is CURRENTLY assigned to (M1).
    return query.filter(_active_assignment(caller.staff.id))


def _staff_names(db: Session, staff_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not staff_ids:
        return {}
    rows = db.query(Staff.id, User.full_name).join(User, User.id == Staff.user_id).filter(Staff.id.in_(staff_ids)).all()
    return {staff_id: name for staff_id, name in rows}


def _to_public(db: Session, rows: list[Any], caller: Caller | None) -> list[ConversationPublic]:
    staff_side = caller is not None and caller.side == "staff"
    names = (
        _staff_names(
            db,
            {
                staff_id
                for row in rows
                for staff_id in (row[0].escalated_by_staff_id, row[0].closed_by_staff_id)
                if staff_id is not None
            },
        )
        if staff_side
        else {}
    )
    result = []
    for row in rows:
        conversation: Conversation = row[0]
        result.append(
            ConversationPublic(
                id=conversation.id,
                # Staff only: the patient is shown names, never internal identifiers.
                clinic_id=conversation.clinic_id if staff_side else None,
                patient_id=conversation.patient_id if staff_side else None,
                staff_id=conversation.staff_id if staff_side else None,
                patient_name=row.patient_name,
                staff_name=row.staff_name,
                status=conversation.status,
                closed_at=conversation.closed_at,
                unread_count=row.unread_count,
                can_reply=bool(row.can_reply),
                team=(
                    ConversationTeamState(
                        needs_doctor_review=conversation.needs_doctor_review,
                        escalated_at=conversation.escalated_at if conversation.needs_doctor_review else None,
                        escalated_by_name=(
                            names.get(conversation.escalated_by_staff_id)
                            if conversation.needs_doctor_review and conversation.escalated_by_staff_id
                            else None
                        ),
                        closed_by_name=(
                            names.get(conversation.closed_by_staff_id) if conversation.closed_by_staff_id else None
                        ),
                    )
                    if staff_side
                    else None
                ),
                created_at=conversation.created_at,
                updated_at=conversation.updated_at,
            )
        )
    return result


def _visible_row(db: Session, conversation_id: uuid.UUID, user: User, caller: Caller | None) -> Any:
    row = _summary_query(db, user, caller).filter(Conversation.id == conversation_id).first()
    if row is None:
        raise _not_found()
    return row


def _summary(db: Session, conversation_id: uuid.UUID, user: User) -> ConversationPublic:
    caller = _caller(db, user)
    return _to_public(db, [_visible_row(db, conversation_id, user, caller)], caller)[0]


def get_conversation_for_user(db: Session, conversation_id: uuid.UUID, user: User) -> Conversation:
    """The conversation when visible to the caller under the access rule above, else 404."""
    conversation: Conversation = _visible_row(db, conversation_id, user, _caller(db, user))[0]
    return conversation


def _locked(db: Session, conversation: Conversation) -> Conversation:
    """Serialize concurrent messages, status changes and escalations of one conversation."""
    db.refresh(conversation, with_for_update=True)
    return conversation


def _resolve_participants(
    db: Session, payload: ConversationCreateRequest, user: User
) -> tuple[Patient, Staff]:
    """Only clinical staff open threads (M4), with the messaging permission AND an
    active care assignment to that patient (M3), via the central policy."""
    if user.role == UserRole.PATIENT:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_PATIENTS_CANNOT_START)
    patient = clinical_access(db, payload.patient_id, user, ClinicalAction.CREATE_CONVERSATIONS)
    staff = staff_profile(db, user)
    if staff is None:  # unreachable after clinical_access; keeps the type narrow
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_NO_MESSAGING)
    return patient, staff


@dataclass(frozen=True)
class StartResult:
    conversation: ConversationPublic
    created: bool
    # Set when starting an existing, closed thread reopened it (audited as a status change).
    reopened_from: ConversationStatus | None = None


def create_conversation(db: Session, payload: ConversationCreateRequest, user: User) -> StartResult:
    """Start a conversation. An existing pair is returned, not duplicated; a closed
    one is reopened, because starting a conversation is a new clinical contact."""
    patient, staff = _resolve_participants(db, payload, user)
    existing = (
        db.query(Conversation)
        .filter(Conversation.patient_id == patient.id, Conversation.staff_id == staff.id)
        .first()
    )
    if existing is not None:
        _locked(db, existing)
        reopened = None
        if existing.status == ConversationStatus.CLOSED:
            reopened = existing.status
            existing.status = ConversationStatus.OPEN
            existing.closed_at = None
            existing.closed_by_staff_id = None
        db.commit()
        return StartResult(_summary(db, existing.id, user), created=False, reopened_from=reopened)
    conversation = Conversation(clinic_id=user.clinic_id, patient_id=patient.id, staff_id=staff.id)
    db.add(conversation)
    try:
        db.commit()
    except IntegrityError:
        # Concurrent create of the same pair: the unique constraint won.
        db.rollback()
        existing = (
            db.query(Conversation)
            .filter(Conversation.patient_id == patient.id, Conversation.staff_id == staff.id)
            .one()
        )
        return StartResult(_summary(db, existing.id, user), created=False)
    return StartResult(_summary(db, conversation.id, user), created=True)


def list_conversations(
    db: Session,
    user: User,
    *,
    offset: int = 0,
    limit: int = 50,
    status_filter: ConversationStatus | None = None,
    needs_review: bool | None = None,
) -> tuple[list[ConversationPublic], int]:
    caller = _caller(db, user)
    if caller is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_NO_MESSAGING)
    query = _summary_query(db, user, caller)
    if status_filter is not None:
        query = query.filter(Conversation.status == status_filter)
    # Triage metadata is staff-only: a patient asking for it simply gets no filter.
    if needs_review is not None and caller.side == "staff":
        query = query.filter(Conversation.needs_doctor_review.is_(needs_review))
    total = query.count()
    rows = (
        query.order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return _to_public(db, rows, caller), total


def _sender_role(sender_user_id: uuid.UUID, patient_user_id: uuid.UUID, staff_roles: dict[uuid.UUID, StaffRole]) -> SenderRole:
    if sender_user_id == patient_user_id:
        return "patient"
    role = staff_roles.get(sender_user_id)
    if role == StaffRole.DOCTOR:
        return "doctor"
    if role == StaffRole.NURSE:
        return "nurse"
    return "staff"


def get_conversation_detail(
    db: Session, conversation_id: uuid.UUID, user: User, *, offset: int = 0, limit: int = 50
) -> tuple[ConversationDetail, int]:
    summary = _summary(db, conversation_id, user)
    query = db.query(Message).filter(
        Message.conversation_id == summary.id, Message.clinic_id == user.clinic_id
    )
    total = query.count()
    messages = query.order_by(Message.created_at.desc(), Message.id.desc()).offset(offset).limit(limit).all()
    # From the conversation row: `summary.patient_id` is withheld from patient callers.
    patient_user_id = (
        db.query(Patient.user_id)
        .join(Conversation, Conversation.patient_id == Patient.id)
        .filter(Conversation.id == summary.id)
        .scalar()
    )
    sender_ids = {message.sender_user_id for message in messages}
    names: dict[uuid.UUID, str] = {}
    staff_roles: dict[uuid.UUID, StaffRole] = {}
    if sender_ids:
        names = {user_id: name for user_id, name in db.query(User.id, User.full_name).filter(User.id.in_(sender_ids))}
        staff_roles = {
            user_id: role
            for user_id, role in db.query(Staff.user_id, Staff.staff_role).filter(
                Staff.user_id.in_(sender_ids), Staff.clinic_id == user.clinic_id
            )
        }
    detail = ConversationDetail(
        **summary.model_dump(),
        messages=[
            MessagePublic(
                id=message.id,
                conversation_id=message.conversation_id,
                sender_name=names.get(message.sender_user_id, "Utilizador"),
                sender_role=_sender_role(message.sender_user_id, patient_user_id, staff_roles),
                is_mine=message.sender_user_id == user.id,
                body=message.body,
                read_at=message.read_at,
                created_at=message.created_at,
            )
            for message in messages
        ],
    )
    return detail, total


def _team_recipients(db: Session, conversation: Conversation, roles: tuple[StaffRole, ...]) -> list[uuid.UUID]:
    """User ids of the patient's active care team members with one of `roles` (server-side only)."""
    rows = (
        db.query(Staff.user_id)
        .join(User, User.id == Staff.user_id)
        .join(
            ClinicalCareAssignment,
            and_(
                ClinicalCareAssignment.staff_id == Staff.id,
                ClinicalCareAssignment.patient_id == conversation.patient_id,
                ClinicalCareAssignment.clinic_id == conversation.clinic_id,
                ClinicalCareAssignment.active.is_(True),
            ),
        )
        .filter(Staff.clinic_id == conversation.clinic_id, Staff.staff_role.in_(roles), User.is_active.is_(True))
        .distinct()
        .all()
    )
    return [user_id for (user_id,) in rows]


@dataclass(frozen=True)
class SendResult:
    message: Message
    # A doctor's reply resolved a pending review request (audited by the router).
    escalation_cleared: bool


def send_message(db: Session, conversation_id: uuid.UUID, body: str, user: User) -> SendResult:
    caller = _caller(db, user)
    row = _visible_row(db, conversation_id, user, caller)
    conversation: Conversation = _locked(db, row[0])
    if conversation.status == ConversationStatus.CLOSED:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=CLOSED_CONVERSATION)
    if not row.can_reply:
        # M2: enforced here, not only hidden in the UI. Nobody could read the reply.
        db.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=INACTIVE_CONVERSATION)
    patient = db.get(Patient, conversation.patient_id)
    if patient is None or caller is None:
        raise _not_found()
    from_patient = patient.user_id == user.id

    message = Message(
        conversation_id=conversation.id,
        clinic_id=conversation.clinic_id,
        sender_user_id=user.id,
        body=body,
    )
    db.add(message)
    # now() is the transaction timestamp, so this equals message.created_at.
    conversation.updated_at = func.now()
    conversation.status = ConversationStatus.WAITING_FOR_TEAM if from_patient else ConversationStatus.WAITING_FOR_PATIENT
    escalation_cleared = False
    if (
        not from_patient
        and conversation.needs_doctor_review
        and caller.staff is not None
        and caller.staff.staff_role in _DOCTOR_ROLES
    ):
        conversation.needs_doctor_review = False
        escalation_cleared = True
    db.flush()
    recipients = _team_recipients(db, conversation, _REPLY_ROLES) if from_patient else [patient.user_id]
    for recipient_user_id in recipients:
        if recipient_user_id == user.id:
            continue
        notify(
            db,
            NotificationEvent.MESSAGE_RECEIVED,
            clinic_id=conversation.clinic_id,
            recipient_user_id=recipient_user_id,
            # Deep link to the specific conversation (M6); access is re-checked on open.
            target=NotificationTarget(TargetType.CONVERSATION, conversation.id),
            dedupe_key=str(message.id),
            # A burst of messages leaves one unread notification per conversation.
            coalesce_unread=True,
        )
    # Message, status, activity timestamp and notifications commit together or not at all.
    db.commit()
    db.refresh(message)
    return SendResult(message, escalation_cleared)


def _staff_caller(db: Session, user: User) -> Staff:
    caller = _caller(db, user)
    if caller is None or caller.staff is None:
        # Patients and non-clinical roles: same answer as an unknown conversation.
        raise _not_found()
    return caller.staff


def change_status(
    db: Session, conversation_id: uuid.UUID, new_status: ConversationStatus, user: User
) -> tuple[ConversationPublic, ConversationStatus | None]:
    """Returns the conversation and the previous status, or None when nothing changed."""
    staff = _staff_caller(db, user)
    conversation = _locked(db, get_conversation_for_user(db, conversation_id, user))
    previous = conversation.status
    if previous == new_status:
        db.rollback()
        return _summary(db, conversation_id, user), None
    can_manage = has_role_action(staff.staff_role, ClinicalAction.MANAGE_CONVERSATIONS)
    can_triage = has_role_action(staff.staff_role, ClinicalAction.TRIAGE_CONVERSATIONS)
    # Closing and reopening are a doctor's decision; triage moves between the open states.
    touches_closed = ConversationStatus.CLOSED in {previous, new_status}
    if not (can_manage or (can_triage and not touches_closed and new_status in _TRIAGE_STATUSES)):
        db.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_NOT_ALLOWED_STATUS)
    conversation.status = new_status
    if new_status == ConversationStatus.CLOSED:
        conversation.closed_at = datetime.now(UTC)
        conversation.closed_by_staff_id = staff.id
        # Closing resolves any outstanding review request.
        conversation.needs_doctor_review = False
        patient_user_id = db.query(Patient.user_id).filter(Patient.id == conversation.patient_id).scalar()
        db.flush()
        notify(
            db,
            NotificationEvent.CONVERSATION_CLOSED,
            clinic_id=conversation.clinic_id,
            recipient_user_id=patient_user_id,
            target=NotificationTarget(TargetType.CONVERSATION, conversation.id),
            dedupe_key=f"{conversation.id}:{conversation.closed_at.isoformat()}",
        )
    else:
        conversation.closed_at = None
        conversation.closed_by_staff_id = None
    db.commit()
    return _summary(db, conversation_id, user), previous


def escalate(db: Session, conversation_id: uuid.UUID, user: User) -> tuple[ConversationPublic, bool]:
    """A nurse asks the care team's doctors to review. Returns (conversation, changed)."""
    staff = _staff_caller(db, user)
    conversation = _locked(db, get_conversation_for_user(db, conversation_id, user))
    if not has_role_action(staff.staff_role, ClinicalAction.ESCALATE_CONVERSATIONS):
        db.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_ONLY_NURSES_ESCALATE)
    if conversation.status == ConversationStatus.CLOSED:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=CLOSED_CONVERSATION)
    if conversation.needs_doctor_review:
        # Already pending: a repeated request is not a new escalation.
        db.rollback()
        return _summary(db, conversation_id, user), False
    conversation.needs_doctor_review = True
    conversation.escalated_at = datetime.now(UTC)
    conversation.escalated_by_staff_id = staff.id
    db.flush()
    for recipient_user_id in _team_recipients(db, conversation, _DOCTOR_ROLES):
        notify(
            db,
            NotificationEvent.CONVERSATION_ESCALATED,
            clinic_id=conversation.clinic_id,
            recipient_user_id=recipient_user_id,
            target=NotificationTarget(TargetType.CONVERSATION, conversation.id),
            dedupe_key=f"{conversation.id}:{conversation.escalated_at.isoformat()}",
        )
    db.commit()
    return _summary(db, conversation_id, user), True


def mark_conversation_read(db: Session, conversation_id: uuid.UUID, user: User) -> int:
    """Marks the other side's unread messages as read. Never touches the caller's own side:
    the patient reads team messages; any care-team member reading clears the team flag
    on patient messages (staff never mark each other's messages)."""
    conversation = get_conversation_for_user(db, conversation_id, user)
    patient_user_id = db.query(Patient.user_id).filter(Patient.id == conversation.patient_id).scalar()
    other_side = Message.sender_user_id != user.id if user.role == UserRole.PATIENT else Message.sender_user_id == patient_user_id
    updated = db.execute(
        update(Message)
        .where(
            Message.conversation_id == conversation.id,
            Message.clinic_id == user.clinic_id,
            other_side,
            Message.read_at.is_(None),
        )
        .values(read_at=datetime.now(UTC))
        .returning(Message.id)
    ).all()
    db.commit()
    return len(updated)
