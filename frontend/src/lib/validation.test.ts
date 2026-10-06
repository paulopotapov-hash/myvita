import { describe, expect, it } from 'vitest'
import {
  appointmentCreateSchema,
  appointmentUpdateSchema,
  consentCreateSchema,
  medicalRecordSchema,
  medicationFormSchema,
  mfaCodeSchema,
  mfaVerificationCodeSchema,
  patientUpdateSchema,
  zodErrorsToRecord,
} from './validation'

const validMedication = {
  name: 'Amoxicilina',
  dosage: '500 mg',
  route: '',
  frequency: '',
  instructions: '',
  start_date: '2026-09-24',
  end_date: '',
}

function errorsOf(result: { success: boolean; error?: import('zod').ZodError }) {
  return result.error ? zodErrorsToRecord(result.error) : {}
}

describe('medicationFormSchema', () => {
  it('accepts the minimum backend-valid medication and trims text', () => {
    const result = medicationFormSchema.safeParse({ ...validMedication, name: '  Amoxicilina  ' })
    expect(result.success).toBe(true)
    expect(result.data?.name).toBe('Amoxicilina')
  })

  it('names the missing required fields', () => {
    const errors = errorsOf(medicationFormSchema.safeParse({ ...validMedication, name: '  ', dosage: '', start_date: '' }))
    expect(errors).toEqual({
      name: 'Indica o nome do medicamento.',
      dosage: 'Indica a dosagem.',
      start_date: 'Indica a data de início.',
    })
  })

  it('mirrors the backend length limits', () => {
    const errors = errorsOf(
      medicationFormSchema.safeParse({
        ...validMedication,
        name: 'x'.repeat(201),
        dosage: 'x'.repeat(201),
        route: 'x'.repeat(101),
        frequency: 'x'.repeat(101),
        instructions: 'x'.repeat(2001),
      }),
    )
    expect(Object.keys(errors).sort()).toEqual(['dosage', 'frequency', 'instructions', 'name', 'route'])
  })

  it('rejects an end date before the start date, mirroring the database constraint', () => {
    const errors = errorsOf(medicationFormSchema.safeParse({ ...validMedication, end_date: '2026-09-23' }))
    expect(errors.end_date).toBe('A data de fim não pode ser anterior à data de início.')
    expect(medicationFormSchema.safeParse({ ...validMedication, end_date: '2026-09-24' }).success).toBe(true)
  })
})

describe('medicalRecordSchema', () => {
  it('requires title and content and enforces backend limits', () => {
    expect(errorsOf(medicalRecordSchema.safeParse({ title: ' ', content: '' }))).toEqual({
      title: 'Indica o título do registo.',
      content: 'Indica o conteúdo clínico.',
    })
    expect(Object.keys(errorsOf(medicalRecordSchema.safeParse({ title: 'x'.repeat(201), content: 'x'.repeat(20_001) })))).toEqual([
      'title',
      'content',
    ])
    expect(medicalRecordSchema.parse({ title: ' A ', content: ' B ' })).toEqual({ title: 'A', content: 'B' })
  })
})

describe('appointment schemas', () => {
  const base = { patient_id: 'p', staff_id: 's', scheduled_at: '2026-10-20T10:30', duration_minutes: '30', reason: '' }

  it('uses the same duration message on create and update', () => {
    const create = errorsOf(appointmentCreateSchema.safeParse({ ...base, duration_minutes: '4' }))
    const update = errorsOf(appointmentUpdateSchema.safeParse({ duration_minutes: '4', reason: '' }))
    expect(create.duration_minutes).toBe('A duração mínima é de 5 minutos.')
    expect(update.duration_minutes).toBe(create.duration_minutes)
    expect(errorsOf(appointmentUpdateSchema.safeParse({ duration_minutes: '481', reason: '' })).duration_minutes).toBe(
      'A duração máxima é de 480 minutos.',
    )
    expect(errorsOf(appointmentUpdateSchema.safeParse({ duration_minutes: '30.5', reason: '' })).duration_minutes).toBe(
      'A duração deve ser um número inteiro de minutos.',
    )
    expect(errorsOf(appointmentUpdateSchema.safeParse({ duration_minutes: '', reason: '' })).duration_minutes).toBeDefined()
  })

  it('requires patient, professional and time on create and limits the reason', () => {
    expect(errorsOf(appointmentCreateSchema.safeParse({ ...base, patient_id: '', staff_id: '', scheduled_at: '' }))).toEqual({
      patient_id: 'Escolhe um paciente.',
      staff_id: 'Escolhe um profissional.',
      scheduled_at: 'Escolhe data e hora.',
    })
    expect(errorsOf(appointmentUpdateSchema.safeParse({ duration_minutes: '30', reason: 'x'.repeat(501) })).reason).toBe(
      'O motivo pode ter no máximo 500 caracteres.',
    )
  })
})

describe('other clinical schemas', () => {
  it('requires a consent purpose and caps it at 500 characters', () => {
    expect(errorsOf(consentCreateSchema.safeParse({ consent_type: 'treatment', purpose: '   ' })).purpose).toBe(
      'Indica a finalidade do consentimento.',
    )
    expect(errorsOf(consentCreateSchema.safeParse({ consent_type: 'treatment', purpose: 'x'.repeat(501) })).purpose).toBe(
      'A finalidade pode ter no máximo 500 caracteres.',
    )
  })

  it('caps patient contact fields at the backend limit of 30', () => {
    expect(patientUpdateSchema.safeParse({ phone: '912345678', national_health_number: '' }).success).toBe(true)
    expect(Object.keys(errorsOf(patientUpdateSchema.safeParse({ phone: '9'.repeat(31), national_health_number: '1'.repeat(31) })))).toEqual([
      'phone',
      'national_health_number',
    ])
  })

  it('validates MFA codes: strict 6 digits for enrolment, code-or-recovery for login', () => {
    expect(mfaCodeSchema.safeParse(' 123456 ').success).toBe(true)
    expect(mfaCodeSchema.safeParse('12345').success).toBe(false)
    expect(mfaCodeSchema.safeParse('abcdef').success).toBe(false)
    expect(mfaVerificationCodeSchema.safeParse('abcd-efgh-ijkl').success).toBe(true)
    expect(mfaVerificationCodeSchema.safeParse('123').success).toBe(false)
  })
})
