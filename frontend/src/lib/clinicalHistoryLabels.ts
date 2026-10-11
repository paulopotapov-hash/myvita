import type { AllergySeverity, ClinicalHistoryFields, ConditionStatus, HistoryCategory } from '../types/api'

/** Order of the categories on the page (medication has its own section, from `medications`). */
export const HISTORY_CATEGORIES: HistoryCategory[] = ['condition', 'procedure', 'allergy', 'immunization', 'note']

export const CATEGORY_LABELS: Record<HistoryCategory, string> = {
  condition: 'Doenças e problemas de saúde',
  procedure: 'Cirurgias e procedimentos',
  allergy: 'Alergias',
  immunization: 'Vacinas',
  note: 'Outras notas',
}

/** What to call one entry of the category in buttons ("Adicionar alergia"). */
export const CATEGORY_SINGULAR: Record<HistoryCategory, string> = {
  condition: 'doença ou problema',
  procedure: 'cirurgia ou procedimento',
  allergy: 'alergia',
  immunization: 'vacina',
  note: 'nota',
}

export const CONDITION_STATUS_LABELS: Record<ConditionStatus, string> = { active: 'Ativa', resolved: 'Resolvida' }

export const SEVERITY_LABELS: Record<AllergySeverity, string> = {
  mild: 'Ligeira',
  moderate: 'Moderada',
  severe: 'Grave',
  unknown: 'Gravidade desconhecida',
}

export const ORIGIN_LABELS = {
  confirmed: 'Confirmado pelo profissional',
  declared: 'Declarado pelo paciente',
} as const

export function originLabel(entry: { confirmed: boolean }): string {
  return entry.confirmed ? ORIGIN_LABELS.confirmed : ORIGIN_LABELS.declared
}

/** Fields each category uses, mirroring the backend (and its database CHECKs). */
export const CATEGORY_FIELDS: Record<HistoryCategory, Array<keyof ClinicalHistoryFields>> = {
  condition: ['name', 'condition_status', 'onset', 'resolved'],
  procedure: ['name', 'occurred', 'location'],
  allergy: ['name', 'reaction', 'severity'],
  immunization: ['name', 'occurred'],
  note: ['note_text'],
}
