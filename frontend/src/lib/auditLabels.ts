/** Human labels for backend AuditAction values (app/models/audit_log.py). Unknown values fall back to the raw key. */
export const AUDIT_ACTION_LABELS: Record<string, string> = {
  login_success: 'Início de sessão',
  login_failure: 'Falha de início de sessão',
  logout: 'Fim de sessão',
  password_change: 'Alteração de palavra-passe',
  invitation_created: 'Convite criado',
  invitation_accepted: 'Convite aceite',
  user_created: 'Utilizador criado',
  user_disabled: 'Utilizador desativado',
  patient_created: 'Paciente criado',
  patient_updated: 'Paciente atualizado',
  patient_deleted: 'Paciente eliminado',
  staff_created: 'Profissional criado',
  staff_updated: 'Profissional atualizado',
  appointment_created: 'Consulta criada',
  appointment_updated: 'Consulta atualizada',
  appointment_cancelled: 'Consulta cancelada',
  clinic_created: 'Clínica criada',
  consent_granted: 'Consentimento concedido',
  consent_revoked: 'Consentimento revogado',
  consent_viewed: 'Consentimento consultado',
  medical_record_created: 'Registo clínico criado',
  medical_record_updated: 'Registo clínico atualizado',
  medical_record_viewed: 'Registo clínico consultado',
  medication_created: 'Medicação criada',
  medication_updated: 'Medicação atualizada',
  medication_deactivated: 'Medicação terminada',
  medication_viewed: 'Medicação consultada',
  notification_read: 'Notificação lida',
  conversation_created: 'Conversa criada',
  conversation_viewed: 'Conversa consultada',
  message_sent: 'Mensagem enviada',
  message_read: 'Mensagens lidas',
  document_uploaded: 'Documento carregado',
  document_downloaded: 'Documento transferido',
  document_deleted: 'Documento eliminado',
  staff_viewed_patient: 'Ficha de paciente consultada',
  staff_viewed_appointment: 'Consulta consultada',
  patient_viewed_own_record: 'Paciente consultou os próprios dados',
  permission_denied: 'Permissão negada',
  csrf_failure: 'Falha CSRF',
  rate_limited: 'Limite de pedidos atingido',
  audit_log_viewed: 'Registo de auditoria consultado',
}

export const AUDIT_RESULT_LABELS = { success: 'Sucesso', failure: 'Falha', denied: 'Negado' } as const

export const AUDIT_RESOURCE_TYPES = [
  'user', 'patient', 'staff', 'clinic', 'appointment', 'appointment_list', 'medical_record', 'medical_record_list',
  'medication', 'medication_list', 'consent', 'consent_list', 'notification', 'conversation', 'message', 'document',
  'invitation', 'audit_log',
] as const

export function auditActionLabel(action: string): string {
  return AUDIT_ACTION_LABELS[action] ?? action
}
