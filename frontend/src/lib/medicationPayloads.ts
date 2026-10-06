import type { MedicationFormValues } from './validation'
import type { MedicationCreateRequest, MedicationPublic, MedicationUpdateRequest } from '../types/api'

export const EMPTY_MEDICATION_FORM: MedicationFormValues = {
  name: '',
  dosage: '',
  route: '',
  frequency: '',
  instructions: '',
  start_date: '',
  end_date: '',
}

export function medicationToForm(medication: MedicationPublic): MedicationFormValues {
  return {
    name: medication.name,
    dosage: medication.dosage,
    route: medication.route ?? '',
    frequency: medication.frequency ?? '',
    instructions: medication.instructions ?? '',
    start_date: medication.start_date,
    end_date: medication.end_date ?? '',
  }
}

/** Optional text the backend rejects when empty is omitted instead of sent as ''. */
export function toCreatePayload(values: MedicationFormValues): MedicationCreateRequest {
  return {
    name: values.name,
    dosage: values.dosage,
    start_date: values.start_date,
    ...(values.route ? { route: values.route } : {}),
    ...(values.frequency ? { frequency: values.frequency } : {}),
    ...(values.instructions ? { instructions: values.instructions } : {}),
    ...(values.end_date ? { end_date: values.end_date } : {}),
  }
}

/** Sends only what changed; emptied optional fields become `null` (the backend's way to clear them). */
export function toUpdatePayload(values: MedicationFormValues, original: MedicationPublic): MedicationUpdateRequest {
  const before = medicationToForm(original)
  const payload: MedicationUpdateRequest = {}
  if (values.name !== before.name) payload.name = values.name
  if (values.dosage !== before.dosage) payload.dosage = values.dosage
  if (values.start_date !== before.start_date) payload.start_date = values.start_date
  if (values.route !== before.route) payload.route = values.route || null
  if (values.frequency !== before.frequency) payload.frequency = values.frequency || null
  if (values.instructions !== before.instructions) payload.instructions = values.instructions || null
  if (values.end_date !== before.end_date) payload.end_date = values.end_date || null
  return payload
}
