import type { ClinicalResultCategory } from '../types/api'

export const RESULT_CATEGORY_LABELS: Record<ClinicalResultCategory, string> = {
  laboratory: 'Análises laboratoriais',
  imaging: 'Imagiologia',
  pathology: 'Anatomia patológica',
  other: 'Outro',
}

export interface ResultFormState {
  category: ClinicalResultCategory
  title: string
  value: string
  unit: string
  reference_range: string
  summary: string
  result_date: string
  document_id: string
  release: boolean
  /** Corrections only: why the released result is being corrected (staff-only). */
  correction_reason: string
}

export const EMPTY_RESULT_FORM: ResultFormState = {
  category: 'laboratory',
  title: '',
  value: '',
  unit: '',
  reference_range: '',
  summary: '',
  result_date: '',
  document_id: '',
  release: false,
  correction_reason: '',
}

export function todayIso(): string {
  const now = new Date()
  const offset = now.getTimezoneOffset() * 60_000
  return new Date(now.getTime() - offset).toISOString().slice(0, 10)
}

export const CORRECTION_REASON_MIN = 5

/** Client-side checks mirroring the backend rules; the backend remains authoritative. */
export function validateResultForm(form: ResultFormState, options: { correction?: boolean } = {}): Record<string, string> {
  const errors: Record<string, string> = {}
  if (options.correction && form.correction_reason.trim().length < CORRECTION_REASON_MIN) {
    errors.correction_reason = `Indica o motivo da correção (pelo menos ${CORRECTION_REASON_MIN} caracteres).`
  }
  if (!form.title.trim()) errors.title = 'Indica a designação do resultado.'
  if (!form.result_date) errors.result_date = 'Indica a data do resultado.'
  else if (form.result_date > todayIso()) errors.result_date = 'A data do resultado não pode ser futura.'
  if (!form.value.trim() && !form.summary.trim() && !form.document_id) {
    errors.value = 'Indica um valor, um resumo ou um documento associado.'
  }
  if (!form.value.trim() && (form.unit.trim() || form.reference_range.trim())) {
    errors.unit = 'A unidade e o intervalo de referência exigem um valor.'
  }
  return errors
}
