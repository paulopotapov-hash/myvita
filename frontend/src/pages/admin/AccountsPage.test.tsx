import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../lib/apiClient'
import { AccountsPage } from './AccountsPage'
import { authService } from '../../services/auth'
import { usersService } from '../../services/users'
import type { AccountSummary } from '../../types/api'

vi.mock('../../services/auth')
vi.mock('../../services/users', async (importOriginal) => {
  const original = await importOriginal<typeof import('../../services/users')>()
  return {
    ...original,
    usersService: {
      list: vi.fn(),
      deactivate: vi.fn(),
      reactivate: vi.fn(),
      issuePasswordReset: vi.fn(),
      requirePasswordChange: vi.fn(),
      resetMfa: vi.fn(),
    },
  }
})

const base = { staff_role: null, is_active: true, mfa_enabled: false, must_change_password: false }
const accounts: AccountSummary[] = [
  { ...base, id: 'me', full_name: 'Eu Admin', role: 'clinic_admin', email: 'eu@clinica.pt' },
  { ...base, id: 'other-admin', full_name: 'Outro Admin', role: 'clinic_admin', email: 'outro@clinica.pt' },
  { ...base, id: 'nurse', full_name: 'Enf. Rui', role: 'staff', staff_role: 'nurse', email: 'rui@clinica.pt', mfa_enabled: true },
  { ...base, id: 'patient', full_name: 'Paciente Ana', role: 'patient', email: null },
]

function renderPage() {
  vi.mocked(authService.me).mockResolvedValue({
    id: 'me',
    email: 'eu@clinica.pt',
    full_name: 'Eu Admin',
    role: 'clinic_admin',
    clinic_id: 'c1',
    staff_role: null,
    patient_id: null,
  })
  vi.mocked(usersService.list).mockResolvedValue({ items: accounts, total: accounts.length })
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AccountsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function row(name: string) {
  return screen.getByText(new RegExp(name)).closest('li') as HTMLElement
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.spyOn(window, 'confirm').mockReturnValue(true)
})

describe('AccountsPage', () => {
  it('offers credential recovery only where the backend allows it', async () => {
    renderPage()
    await screen.findByText('Enf. Rui')
    expect(within(row('Eu Admin')).queryAllByRole('button')).toHaveLength(0)
    expect(within(row('Outro Admin')).queryByRole('button', { name: 'Ligação de redefinição' })).not.toBeInTheDocument()
    expect(within(row('Outro Admin')).getByRole('button', { name: 'Desativar' })).toBeInTheDocument()
    expect(within(row('Enf. Rui')).getByRole('button', { name: 'Repor 2FA' })).toBeInTheDocument()
    expect(within(row('Paciente Ana')).queryByRole('button', { name: 'Repor 2FA' })).not.toBeInTheDocument()
    expect(within(row('Paciente Ana')).queryByText(/@/)).not.toBeInTheDocument()
  })

  it('shows an issued reset link once, with the token only in the URL fragment', async () => {
    vi.mocked(usersService.issuePasswordReset).mockResolvedValue({
      user_id: 'nurse',
      token: 'tok_123',
      expires_at: '2026-10-06T12:00:00Z',
    })
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Enf. Rui')
    await user.click(within(row('Enf. Rui')).getByRole('button', { name: 'Ligação de redefinição' }))

    expect(usersService.issuePasswordReset).toHaveBeenCalledWith('nurse')
    expect(await screen.findByText(`${window.location.origin}/redefinir-palavra-passe#token=tok_123`)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Fechar' }))
    expect(screen.queryByText(/tok_123/)).not.toBeInTheDocument()
  })

  it('does nothing when the admin cancels the confirmation', async () => {
    vi.mocked(window.confirm).mockReturnValue(false)
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Enf. Rui')
    await user.click(within(row('Enf. Rui')).getByRole('button', { name: 'Desativar' }))
    expect(usersService.deactivate).not.toHaveBeenCalled()
  })

  it('confirms a completed action with a success message and refreshes the list', async () => {
    vi.mocked(usersService.deactivate).mockResolvedValue(accounts[2])
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Enf. Rui')
    await user.click(within(row('Enf. Rui')).getByRole('button', { name: 'Desativar' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Conta desativada.')
    expect(usersService.list).toHaveBeenCalledTimes(2)
  })

  it('shows a failed action as an alert and no success message', async () => {
    vi.mocked(usersService.resetMfa).mockRejectedValue(new ApiError(409, 'x', { detail: 'Conta sem 2FA ativa.' }))
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Enf. Rui')
    await user.click(within(row('Enf. Rui')).getByRole('button', { name: 'Repor 2FA' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Conta sem 2FA ativa.')
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})
