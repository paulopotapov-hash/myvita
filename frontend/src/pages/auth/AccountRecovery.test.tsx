import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AccountSetupPage } from './AccountSetupPage'
import { PasswordResetConfirmPage, PasswordResetRequestPage } from './PasswordResetPages'
import { ApiError } from '../../lib/apiClient'
import { authService } from '../../services/auth'

vi.mock('../../services/auth')

function renderWithProviders(ui: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
  return { invalidate }
}

afterEach(() => {
  window.history.replaceState(null, '', '/')
  vi.clearAllMocks()
})

describe('PasswordResetConfirmPage', () => {
  it('reads the token from the URL fragment, removes it from the address bar and submits it', async () => {
    window.history.replaceState(null, '', '/redefinir-palavra-passe#token=abc123')
    vi.mocked(authService.confirmPasswordReset).mockResolvedValue(undefined)
    const user = userEvent.setup()
    renderWithProviders(<PasswordResetConfirmPage />)
    expect(window.location.hash).toBe('')

    await user.type(screen.getByLabelText('Nova palavra-passe'), 'NovaSenhaForte1!')
    await user.type(screen.getByLabelText('Confirmar palavra-passe'), 'NovaSenhaForte1!')
    await user.click(screen.getByRole('button', { name: 'Guardar palavra-passe' }))

    expect(authService.confirmPasswordReset).toHaveBeenCalledWith('abc123', 'NovaSenhaForte1!')
    expect(await screen.findByText(/Palavra-passe alterada/)).toBeInTheDocument()
  })

  it('shows the backend error for a used or expired link', async () => {
    window.history.replaceState(null, '', '/redefinir-palavra-passe#token=used')
    vi.mocked(authService.confirmPasswordReset).mockRejectedValue(
      new ApiError(400, 'Ligação de redefinição inválida ou expirada.', {
        detail: 'Ligação de redefinição inválida ou expirada.',
      }),
    )
    const user = userEvent.setup()
    renderWithProviders(<PasswordResetConfirmPage />)
    await user.type(screen.getByLabelText('Nova palavra-passe'), 'NovaSenhaForte1!')
    await user.type(screen.getByLabelText('Confirmar palavra-passe'), 'NovaSenhaForte1!')
    await user.click(screen.getByRole('button', { name: 'Guardar palavra-passe' }))
    expect(await screen.findByText('Ligação de redefinição inválida ou expirada.')).toBeInTheDocument()
  })

  it('explains a missing token instead of showing a form', () => {
    renderWithProviders(<PasswordResetConfirmPage />)
    expect(screen.getByText('Ligação de redefinição inválida ou incompleta.')).toBeInTheDocument()
    expect(screen.queryByLabelText('Nova palavra-passe')).not.toBeInTheDocument()
  })
})

describe('PasswordResetRequestPage', () => {
  it('shows the same generic answer the backend gives for any address', async () => {
    vi.mocked(authService.requestPasswordReset).mockResolvedValue({ detail: 'Contacte o administrador da sua clínica.' })
    const user = userEvent.setup()
    renderWithProviders(<PasswordResetRequestPage />)
    await user.type(screen.getByLabelText('Email'), 'ana@example.com')
    await user.click(screen.getByRole('button', { name: 'Pedir ajuda' }))
    expect(authService.requestPasswordReset).toHaveBeenCalledWith('ana@example.com')
    expect(await screen.findByText('Contacte o administrador da sua clínica.')).toBeInTheDocument()
  })
})

describe('AccountSetupPage', () => {
  it('changes a forced password and then re-checks the session', async () => {
    vi.mocked(authService.changePassword).mockResolvedValue(undefined)
    const user = userEvent.setup()
    const { invalidate } = renderWithProviders(<AccountSetupPage action="password_change" />)
    await user.type(screen.getByLabelText('Palavra-passe atual'), 'SenhaAntiga1!')
    await user.type(screen.getByLabelText('Nova palavra-passe'), 'NovaSenhaForte1!')
    await user.type(screen.getByLabelText('Confirmar nova palavra-passe'), 'NovaSenhaForte1!')
    await user.click(screen.getByRole('button', { name: 'Alterar palavra-passe' }))

    expect(authService.changePassword).toHaveBeenCalledWith({
      current_password: 'SenhaAntiga1!',
      new_password: 'NovaSenhaForte1!',
    })
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ['session'] }))
  })

  it('enrols MFA and shows the recovery codes once before continuing', async () => {
    vi.mocked(authService.startMfaSetup).mockResolvedValue({
      secret: 'JBSWY3DPEHPK3PXP',
      otpauth_uri: 'otpauth://totp/myVita:ana?secret=JBSWY3DPEHPK3PXP',
    })
    vi.mocked(authService.enableMfa).mockResolvedValue({ recovery_codes: ['abcde-fghjk', 'mnpqr-stuvw'] })
    const user = userEvent.setup()
    const { invalidate } = renderWithProviders(<AccountSetupPage action="mfa_setup" />)

    await user.click(screen.getByRole('button', { name: 'Configurar autenticação de dois fatores' }))
    expect(await screen.findByText('JBSWY3DPEHPK3PXP')).toBeInTheDocument()
    await user.type(screen.getByLabelText('Código de 6 dígitos'), '123456')
    await user.click(screen.getByRole('button', { name: 'Ativar' }))

    expect(authService.enableMfa).toHaveBeenCalledWith('123456')
    expect(await screen.findByText('abcde-fghjk')).toBeInTheDocument()
    expect(invalidate).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Guardei os códigos — continuar' }))
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['session'] })
  })

  it('always lets the user sign out', async () => {
    vi.mocked(authService.logout).mockResolvedValue(undefined)
    const user = userEvent.setup()
    renderWithProviders(<AccountSetupPage action="mfa_verification" />)
    await user.click(screen.getByRole('button', { name: 'Terminar sessão' }))
    expect(authService.logout).toHaveBeenCalled()
  })
})
