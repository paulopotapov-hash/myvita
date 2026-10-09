import { describe, expect, it } from 'vitest'
import { ApiError, NetworkError } from './apiClient'
import { formErrorsFrom, toUserMessage } from './errorMessages'

describe('toUserMessage', () => {
  it.each([
    [401, 'Sessão inválida ou expirada. Inicia sessão novamente.'],
    [403, 'Não tens permissão para aceder a este recurso.'],
    [404, 'Não encontrado.'],
    [409, 'Este registo já existe.'],
    [500, 'Ocorreu um erro no servidor. Tenta novamente mais tarde.'],
  ] as const)('maps HTTP %i to a safe Portuguese message', (status, message) => {
    expect(toUserMessage(new ApiError(status, `HTTP ${status}`))).toBe(message)
  })

  it('prefers the backend safe detail where it supplies actionable context', () => {
    expect(toUserMessage(new ApiError(409, 'conflict', { detail: 'Já existe uma consulta sobreposta.' })))
      .toBe('Já existe uma consulta sobreposta.')
  })

  it('distinguishes network errors from HTTP errors', () => {
    expect(toUserMessage(new NetworkError())).toContain('Sem ligação ao servidor')
  })
})

// Restored from Parent A: dropped when B's file won the add/add conflict, but
// formErrorsFrom is still used by the restored MedicationsSection.
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
