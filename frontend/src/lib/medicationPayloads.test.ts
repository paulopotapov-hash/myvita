import { describe, expect, it } from 'vitest'
import { EMPTY_MEDICATION_FORM, medicationToForm, toCreatePayload, toUpdatePayload } from './medicationPayloads'
import type { MedicationPublic } from '../types/api'

const medication: MedicationPublic = {
  id: 'm1',
  clinic_id: 'c1',
  patient_id: 'p1',
  prescribed_by_staff_id: 's1',
  name: 'Amoxicilina',
  dosage: '500 mg',
  route: 'oral',
  frequency: '8/8h',
  instructions: 'Após as refeições',
  status: 'active',
  start_date: '2026-09-24',
  end_date: null,
  created_at: '2026-09-24T10:00:00Z',
  updated_at: '2026-09-24T10:00:00Z',
}

describe('medication payloads', () => {
  it('omits empty optional fields on create (the backend rejects empty strings)', () => {
    expect(toCreatePayload({ ...EMPTY_MEDICATION_FORM, name: 'A', dosage: '1 mg', start_date: '2026-01-01' })).toEqual({
      name: 'A',
      dosage: '1 mg',
      start_date: '2026-01-01',
    })
  })

  it('sends every filled field on create', () => {
    expect(toCreatePayload(medicationToForm({ ...medication, end_date: '2026-10-01' }))).toEqual({
      name: 'Amoxicilina',
      dosage: '500 mg',
      route: 'oral',
      frequency: '8/8h',
      instructions: 'Após as refeições',
      start_date: '2026-09-24',
      end_date: '2026-10-01',
    })
  })

  it('sends nothing when an edit changes nothing', () => {
    expect(toUpdatePayload(medicationToForm(medication), medication)).toEqual({})
  })

  it('sends only changed fields and clears emptied optional fields with null', () => {
    const edited = { ...medicationToForm(medication), dosage: '250 mg', route: '', end_date: '2026-10-05' }
    expect(toUpdatePayload(edited, medication)).toEqual({ dosage: '250 mg', route: null, end_date: '2026-10-05' })
  })
})
