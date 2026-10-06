import uuid
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import and_
from sqlalchemy.orm import Session, selectinload

from app.core.clinical_access import (
    ClinicalAction,
    clinical_access,
    clinical_staff,
    has_role_action,
    staff_profile,
)
from app.models import (
    ClinicalCareAssignment,
    ClinicalConversation,
    ClinicalMessage,
    ConversationStatus,
    MessageSenderRole,
    Notification,
    Patient,
    Staff,
    StaffRole,
    User,
    UserRole,
)
from app.modules.messaging.schemas import ConversationCreate, ConversationStatusUpdate, MessageCreate


def _get_conversation(
    db: Session, conversation_id: uuid.UUID, user: User, *, lock: bool = False
) -> ClinicalConversation:
    query = db.query(ClinicalConversation).filter(
        ClinicalConversation.id == conversation_id,
        ClinicalConversation.clinic_id == user.clinic_id,
    )
    if lock:
        query = query.with_for_update()
    conversation = query.options(selectinload(ClinicalConversation.messages)).first()
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    clinical_access(db, conversation.patient_id, user, ClinicalAction.VIEW_CONVERSATIONS)
    return conversation


def list_conversations(db: Session, user: User) -> list[ClinicalConversation]:
    query = db.query(ClinicalConversation).filter(ClinicalConversation.clinic_id == user.clinic_id)
    if user.role == UserRole.PATIENT:
        patient = db.query(Patient).filter(Patient.user_id == user.id, Patient.clinic_id == user.clinic_id).first()
        if patient is None:
            return []
        clinical_access(db, patient.id, user, ClinicalAction.VIEW_CONVERSATIONS)
        query = query.filter(ClinicalConversation.patient_id == patient.id)
    else:
        staff = clinical_staff(db, user, action=ClinicalAction.VIEW_CONVERSATIONS)
        query = query.join(
            ClinicalCareAssignment,
            and_(
                ClinicalCareAssignment.patient_id == ClinicalConversation.patient_id,
                ClinicalCareAssignment.clinic_id == ClinicalConversation.clinic_id,
                ClinicalCareAssignment.staff_id == staff.id,
                ClinicalCareAssignment.active.is_(True),
            ),
        )
    conversations = (
        query.options(selectinload(ClinicalConversation.messages))
        .order_by(ClinicalConversation.updated_at.desc(), ClinicalConversation.id.desc())
        .all()
    )
    for conversation in conversations:
        clinical_access(db, conversation.patient_id, user, ClinicalAction.VIEW_CONVERSATIONS)
    return conversations


def get_conversation(db: Session, conversation_id: uuid.UUID, user: User) -> ClinicalConversation:
    conversation = _get_conversation(db, conversation_id, user, lock=True)
    if user.role == UserRole.PATIENT:
        conversation.patient_unread = False
    else:
        conversation.team_unread = False
    db.commit()
    db.refresh(conversation)
    return conversation


def _staff_sender(db: Session, user: User, patient_id: uuid.UUID, action: ClinicalAction) -> Staff:
    return clinical_staff(db, user, patient_id, action)


def _sender_role(db: Session, user: User, patient_id: uuid.UUID, *, creating: bool) -> MessageSenderRole:
    if user.role == UserRole.PATIENT:
        if creating:
            raise HTTPException(status_code=403, detail="Os pacientes não podem iniciar conversas.")
        clinical_access(db, patient_id, user, ClinicalAction.REPLY_CONVERSATIONS)
        return MessageSenderRole.PATIENT
    action = ClinicalAction.CREATE_CONVERSATIONS if creating else ClinicalAction.REPLY_CONVERSATIONS
    staff = _staff_sender(db, user, patient_id, action)
    if staff.staff_role == StaffRole.DOCTOR:
        return MessageSenderRole.DOCTOR
    if staff.staff_role == StaffRole.NURSE:
        return MessageSenderRole.NURSE
    raise HTTPException(status_code=403, detail="Sem permissões clínicas para mensagens.")


def _notify_patient(db: Session, conversation: ClinicalConversation, *, subject: str, updated: bool) -> None:
    patient = db.query(Patient).filter(Patient.id == conversation.patient_id).one()
    db.add(
        Notification(
            clinic_id=conversation.clinic_id,
            user_id=patient.user_id,
            title="Nova mensagem da equipa" if not updated else "Resposta da equipa",
            message=f"Nova mensagem em “{subject}”.",
            target_type="conversation",
            conversation_target_id=conversation.id,
        )
    )


def _authorized_staff_users(
    db: Session, conversation: ClinicalConversation, roles: tuple[StaffRole, ...]
) -> list[User]:
    permitted_roles = tuple(
        role for role in roles if has_role_action(role, ClinicalAction.VIEW_CONVERSATIONS)
    )
    if not permitted_roles:
        return []
    return (
        db.query(User)
        .join(Staff, Staff.user_id == User.id)
        .join(
            ClinicalCareAssignment,
            and_(
                ClinicalCareAssignment.staff_id == Staff.id,
                ClinicalCareAssignment.clinic_id == Staff.clinic_id,
                ClinicalCareAssignment.patient_id == conversation.patient_id,
                ClinicalCareAssignment.active.is_(True),
            ),
        )
        .filter(
            User.clinic_id == conversation.clinic_id,
            User.is_active.is_(True),
            Staff.staff_role.in_(permitted_roles),
        )
        .distinct()
        .all()
    )


def _notify_staff(db: Session, conversation: ClinicalConversation, *, doctors_only: bool = False) -> None:
    roles = (StaffRole.DOCTOR,) if doctors_only else (StaffRole.DOCTOR, StaffRole.NURSE)
    for recipient in _authorized_staff_users(db, conversation, roles):
        db.add(
            Notification(
                clinic_id=conversation.clinic_id,
                user_id=recipient.id,
                title="Resposta do paciente" if not doctors_only else "Conversa escalada para médico",
                message=f"Nova atividade em “{conversation.subject}”.",
                target_type="conversation",
                conversation_target_id=conversation.id,
            )
        )


def _new_message(
    db: Session,
    conversation: ClinicalConversation,
    user: User,
    role: MessageSenderRole,
    body: str,
) -> ClinicalMessage:
    message = ClinicalMessage(
        conversation_id=conversation.id,
        clinic_id=conversation.clinic_id,
        sender_user_id=user.id,
        sender_name=user.full_name,
        sender_role=role,
        body=body.strip(),
    )
    db.add(message)
    return message


def create_conversation(
    db: Session, patient_id: uuid.UUID, payload: ConversationCreate, user: User
) -> ClinicalConversation:
    patient = clinical_access(db, patient_id, user, ClinicalAction.CREATE_CONVERSATIONS)
    staff = _staff_sender(db, user, patient.id, ClinicalAction.CREATE_CONVERSATIONS)
    conversation = ClinicalConversation(
        clinic_id=patient.clinic_id,
        patient_id=patient.id,
        created_by_staff_id=staff.id,
        subject=payload.subject.strip(),
        status=ConversationStatus.WAITING_FOR_PATIENT,
        patient_unread=True,
        team_unread=False,
    )
    db.add(conversation)
    db.flush()
    _new_message(db, conversation, user, _sender_role(db, user, patient.id, creating=True), payload.body)
    _notify_patient(db, conversation, subject=conversation.subject, updated=False)
    db.commit()
    return _get_conversation(db, conversation.id, user)


def send_message(
    db: Session, conversation_id: uuid.UUID, payload: MessageCreate, user: User
) -> tuple[ClinicalConversation, bool]:
    conversation = _get_conversation(db, conversation_id, user, lock=True)
    if conversation.status == ConversationStatus.CLOSED:
        raise HTTPException(status_code=409, detail="A conversa está encerrada.")
    role = _sender_role(db, user, conversation.patient_id, creating=False)
    _new_message(db, conversation, user, role, payload.body)
    conversation.updated_at = datetime.now(UTC)
    if role == MessageSenderRole.PATIENT:
        conversation.status = ConversationStatus.WAITING_FOR_TEAM
        conversation.team_unread = True
        conversation.patient_unread = False
        _notify_staff(db, conversation)
    else:
        conversation.status = ConversationStatus.WAITING_FOR_PATIENT
        conversation.patient_unread = True
        conversation.team_unread = False
        _notify_patient(db, conversation, subject=conversation.subject, updated=True)
        staff = staff_profile(db, user)
        escalation_cleared = False
        if staff and staff.staff_role == StaffRole.DOCTOR and conversation.needs_doctor_review:
            conversation.needs_doctor_review = False
            escalation_cleared = True
    if role == MessageSenderRole.PATIENT:
        escalation_cleared = False
    db.commit()
    return _get_conversation(db, conversation.id, user), escalation_cleared


def update_status(
    db: Session, conversation_id: uuid.UUID, payload: ConversationStatusUpdate, user: User
) -> tuple[ClinicalConversation, bool, ConversationStatus]:
    conversation = _get_conversation(db, conversation_id, user, lock=True)
    staff = clinical_staff(db, user, conversation.patient_id, ClinicalAction.VIEW_CONVERSATIONS)
    can_manage = has_role_action(staff.staff_role, ClinicalAction.MANAGE_CONVERSATIONS)
    can_triage = has_role_action(staff.staff_role, ClinicalAction.TRIAGE_CONVERSATIONS)
    if not (can_manage or can_triage):
        raise HTTPException(status_code=403, detail="Sem permissões para alterar o estado da conversa.")
    if payload.status == ConversationStatus.CLOSED and not can_manage:
        raise HTTPException(status_code=403, detail="Só um médico pode encerrar a conversa.")
    if conversation.status == ConversationStatus.CLOSED and payload.status != ConversationStatus.CLOSED and not can_manage:
        raise HTTPException(status_code=403, detail="Só um médico pode reabrir a conversa.")
    previous = conversation.status
    changed = previous != payload.status
    if changed:
        conversation.status = payload.status
        conversation.closed_at = datetime.now(UTC) if payload.status == ConversationStatus.CLOSED else None
        conversation.updated_at = datetime.now(UTC)
        db.commit()
    return _get_conversation(db, conversation.id, user), changed, previous


def escalate_to_doctor(
    db: Session, conversation_id: uuid.UUID, user: User
) -> tuple[ClinicalConversation, bool]:
    conversation = _get_conversation(db, conversation_id, user, lock=True)
    clinical_staff(db, user, conversation.patient_id, ClinicalAction.ESCALATE_CONVERSATIONS)
    if conversation.status == ConversationStatus.CLOSED:
        raise HTTPException(status_code=409, detail="A conversa está encerrada.")
    changed = not conversation.needs_doctor_review
    if changed:
        if not _authorized_staff_users(db, conversation, (StaffRole.DOCTOR,)):
            raise HTTPException(
                status_code=409,
                detail="Não existe um médico autorizado atribuído a este paciente.",
            )
        conversation.needs_doctor_review = True
        conversation.updated_at = datetime.now(UTC)
        _notify_staff(db, conversation, doctors_only=True)
        db.commit()
    return _get_conversation(db, conversation.id, user), changed
