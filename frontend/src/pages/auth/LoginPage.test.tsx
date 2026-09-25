import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { LoginPage } from './LoginPage'
import { ApiError } from '../../lib/apiClient'
import { safePostLoginPath } from '../../lib/navigation'
import { authService } from '../../services/auth'

vi.mock('../../services/auth')

function renderLoginPage() {
  vi.mocked(authService.me).mockRejectedValue(new ApiError(401, 'unauthorized'))
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const rendered = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/login']}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/app" element={<div>Área autenticada</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return { ...rendered, queryClient }
}

describe('LoginPage', () => {
  it('only accepts internal protected routes as post-login destinations', () => {
    expect(safePostLoginPath({ from: '/app/pacientes?tab=ativos' })).toBe('/app/pacientes?tab=ativos')
    expect(safePostLoginPath({ from: '//evil.example/phishing' })).toBe('/app')
    expect(safePostLoginPath({ from: 'https://evil.example/phishing' })).toBe('/app')
    expect(safePostLoginPath({ from: '/login' })).toBe('/app')
    expect(safePostLoginPath({ from: '/app\\evil.example' })).toBe('/app')
  })

  it('shows validation errors for an empty/invalid form without calling the API', async () => {
    const user = userEvent.setup()
    renderLoginPage()

    await user.type(screen.getByLabelText('Email'), 'not-an-email')
    await user.click(screen.getByRole('button', { name: 'Entrar' }))

    expect(await screen.findByText('Introduz um email válido.')).toBeInTheDocument()
    expect(authService.login).not.toHaveBeenCalled()
  })

  it('submits valid credentials and shows the backend error on failure', async () => {
    vi.mocked(authService.login).mockRejectedValue(
      new ApiError(401, 'Email ou palavra-passe incorretos.', { detail: 'Email ou palavra-passe incorretos.' }),
    )
    const user = userEvent.setup()
    renderLoginPage()

    await user.type(screen.getByLabelText('Email'), 'ana@example.com')
    await user.type(screen.getByLabelText('Palavra-passe'), 'senha-errada')
    await user.click(screen.getByRole('button', { name: 'Entrar' }))

    expect(authService.login).toHaveBeenCalledWith({ email: 'ana@example.com', password: 'senha-errada' })
    expect(await screen.findByText('Email ou palavra-passe incorretos.')).toBeInTheDocument()
  })

  it('redirects to /app after a successful login', async () => {
    vi.mocked(authService.login).mockResolvedValue({
      id: '1',
      email: 'ana@example.com',
      full_name: 'Ana',
      role: 'patient',
      clinic_id: 'c1',
      staff_role: null,
      patient_id: 'p1',
    })
    const user = userEvent.setup()
    const { queryClient } = renderLoginPage()
    queryClient.setQueryData(['patients'], [{ id: 'previous-tenant-patient' }])

    await user.type(screen.getByLabelText('Email'), 'ana@example.com')
    await user.type(screen.getByLabelText('Palavra-passe'), 'senha-correta')
    await user.click(screen.getByRole('button', { name: 'Entrar' }))

    await waitFor(() => expect(screen.getByText('Área autenticada')).toBeInTheDocument())
    expect(queryClient.getQueryData(['patients'])).toBeUndefined()
  })
})
