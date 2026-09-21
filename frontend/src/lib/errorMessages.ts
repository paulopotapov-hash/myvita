import { ApiError, NetworkError } from './apiClient'

/**
 * Turns any error this app might throw into a short, human, Portuguese
 * message safe to show directly in the UI. Never returns anything from
 * the raw error object except the backend's own `detail` (which the
 * backend guarantees is already safe — see backend/app/main.py's
 * exception handlers, which never let stack traces or SQL reach the
 * client in the first place).
 */
export function toUserMessage(error: unknown): string {
  if (error instanceof NetworkError) {
    return 'Sem ligação ao servidor. Verifica a tua internet e tenta novamente.'
  }

  if (error instanceof ApiError) {
    switch (error.status) {
      case 401:
        return error.detail ?? 'Sessão inválida ou expirada. Inicia sessão novamente.'
      case 403:
        return error.detail ?? 'Não tens permissão para aceder a este recurso.'
      case 404:
        return error.detail ?? 'Não encontrado.'
      case 409:
        return error.detail ?? 'Este registo já existe.'
      case 422:
        return 'Verifica os dados introduzidos.'
      case 429:
        return 'Demasiados pedidos em pouco tempo. Espera um momento e tenta novamente.'
      case 503:
        return 'O serviço está temporariamente indisponível. Tenta novamente dentro de instantes.'
      default:
        if (error.status >= 500) {
          return 'Ocorreu um erro no servidor. Tenta novamente mais tarde.'
        }
        return error.detail ?? 'Ocorreu um erro. Tenta novamente.'
    }
  }

  return 'Ocorreu um erro inesperado. Tenta novamente.'
}
