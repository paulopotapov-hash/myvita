import { describe, expect, it } from 'vitest'
import { EMPTY_RESULT_FORM, todayIso, validateResultForm } from './clinicalResultForm'

const valid = { ...EMPTY_RESULT_FORM, title: 'Hemoglobina', value: '13', result_date: '2026-01-01' }

describe('validateResultForm', () => {
  it('accepts a result with a value, a summary or a linked document', () => {
    expect(validateResultForm(valid)).toEqual({})
    expect(validateResultForm({ ...valid, value: '', summary: 'Sem alterações' })).toEqual({})
    expect(validateResultForm({ ...valid, value: '', document_id: 'doc-1' })).toEqual({})
  })

  it('requires a title, a date and some content', () => {
    const errors = validateResultForm({ ...EMPTY_RESULT_FORM, title: '   ' })
    expect(Object.keys(errors).sort()).toEqual(['result_date', 'title', 'value'])
  })

  it('refuses a future clinical date', () => {
    const tomorrow = new Date(Date.now() + 2 * 86_400_000).toISOString().slice(0, 10)
    expect(validateResultForm({ ...valid, result_date: tomorrow }).result_date).toMatch(/futura/)
    expect(validateResultForm({ ...valid, result_date: todayIso() })).toEqual({})
  })

  it('refuses a unit or reference range without a value', () => {
    expect(validateResultForm({ ...valid, value: '', summary: 'x', unit: 'mg' }).unit).toBeTruthy()
    expect(validateResultForm({ ...valid, value: '', summary: 'x', reference_range: '1-2' }).unit).toBeTruthy()
  })
})

describe('validateResultForm for corrections', () => {
  it('requires a meaningful correction reason only for corrections', () => {
    expect(validateResultForm(valid)).toEqual({})
    expect(validateResultForm(valid, { correction: true }).correction_reason).toMatch(/motivo/)
    expect(validateResultForm({ ...valid, correction_reason: '   abc  ' }, { correction: true }).correction_reason).toBeTruthy()
    expect(validateResultForm({ ...valid, correction_reason: 'Erro de transcrição' }, { correction: true })).toEqual({})
  })
})
