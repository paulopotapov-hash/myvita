import { describe, expect, it } from 'vitest'
import { ApiError, NetworkError } from './apiClient'
import { toUserMessage } from './errorMessages'

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
