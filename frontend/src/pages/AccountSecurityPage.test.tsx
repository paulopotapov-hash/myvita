import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../lib/apiClient'
import { authService } from '../services/auth'
import { AccountSecurityPage } from './AccountSecurityPage'

vi.mock('../services/auth')
vi.mock('../hooks/useSession', () => ({
  SESSION_QUERY_KEY: ['session'],
  useSession: () => ({ user: { id: 'u1', mfa_enabled: true } }),
}))

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <AccountSecurityPage />
    </QueryClientProvider>,
  )
  return userEvent.setup()
}

async function fill(user: ReturnType<typeof userEvent.setup>, current: string, next: string, confirm: string) {
  if (current) await user.type(screen.getByLabelText('Palavra-passe atual'), current)
  await user.type(screen.getByLabelText('Nova palavra-passe'), next)
  await user.type(screen.getByLabelText('Confirmar nova palavra-passe'), confirm)
  await user.click(screen.getByRole('button', { name: 'Alterar palavra-passe' }))
}

describe('AccountSecurityPage', () => {
  beforeEach(() => vi.clearAllMocks())

  it('validates the password change next to each field without calling the API', async () => {
    const user = renderPage()
    await fill(user, '', 'curta', 'diferente')
    expect(screen.getByText('Introduz a palavra-passe atual.')).toBeInTheDocument()
    expect(screen.getByText('A palavra-passe precisa de pelo menos 8 caracteres.')).toBeInTheDocument()
    expect(screen.getByText('As palavras-passe não coincidem.')).toBeInTheDocument()
    expect(authService.changePassword).not.toHaveBeenCalled()
  })

  it('confirms a successful change with a status message and clears the fields', async () => {
    vi.mocked(authService.changePassword).mockResolvedValue(undefined as never)
    const user = renderPage()
    await fill(user, 'AntigaSenha123!', 'NovaSenhaForte456!', 'NovaSenhaForte456!')
    expect(await screen.findByRole('status')).toHaveTextContent('Palavra-passe alterada')
    expect(vi.mocked(authService.changePassword).mock.calls[0][0]).toEqual({
      current_password: 'AntigaSenha123!',
      new_password: 'NovaSenhaForte456!',
    })
    expect(screen.getByLabelText('Palavra-passe atual')).toHaveValue('')
  })

  it('shows the backend rejection as an alert', async () => {
    vi.mocked(authService.changePassword).mockRejectedValue(
      new ApiError(400, 'x', { detail: 'Palavra-passe atual incorreta.' }),
    )
    const user = renderPage()
    await fill(user, 'Errada12345!', 'NovaSenhaForte456!', 'NovaSenhaForte456!')
    expect(await screen.findByRole('alert')).toHaveTextContent('Palavra-passe atual incorreta.')
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})
