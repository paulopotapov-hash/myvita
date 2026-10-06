import { describe, expect, it } from 'vitest'
import { ApiError, NetworkError } from './apiClient'
import { formErrorsFrom } from './errorMessages'

const FIELDS = ['name', 'dosage'] as const

describe('formErrorsFrom', () => {
  it('places backend 422 field errors on the matching fields', () => {
    const error = new ApiError(422, 'x', { fieldErrors: { name: 'Campo inválido', dosage: 'Muito longo' } })
    expect(formErrorsFrom(error, FIELDS)).toEqual({ name: 'Campo inválido', dosage: 'Muito longo' })
  })

  it('never drops a field error the form cannot display', () => {
    const error = new ApiError(422, 'x', { fieldErrors: { name: 'Campo inválido', body: 'Erro de modelo' } })
    expect(formErrorsFrom(error, FIELDS)).toEqual({ name: 'Campo inválido', _root: 'Verifica os dados introduzidos.' })
  })

  it('falls back to a root message for non-field errors', () => {
    expect(formErrorsFrom(new ApiError(409, 'x', { detail: 'Já existe uma consulta sobreposta.' }), FIELDS)).toEqual({
      _root: 'Já existe uma consulta sobreposta.',
    })
    expect(formErrorsFrom(new NetworkError(), FIELDS)._root).toMatch(/Sem ligação/)
    expect(formErrorsFrom(new Error('boom'), FIELDS)._root).toBe('Ocorreu um erro inesperado. Tenta novamente.')
  })
})
