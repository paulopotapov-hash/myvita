import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { LoginPage } from './LoginPage'
import { ApiError } from '../../lib/apiClient'
import { authService } from '../../services/auth'

vi.mock('../../services/auth')

function renderLoginPage(initialEntry: string | { pathname: string; state?: unknown } = '/login') {
  vi.mocked(authService.me).mockRejectedValue(new ApiError(401, 'unauthorized'))
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/app" element={<div>Área autenticada</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('LoginPage', () => {
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
    })
    const user = userEvent.setup()
    renderLoginPage()
    vi.mocked(authService.me).mockResolvedValue({
      id: '1',
      email: 'ana@example.com',
      full_name: 'Ana',
      role: 'patient',
      clinic_id: 'c1',
    })

    await user.type(screen.getByLabelText('Email'), 'ana@example.com')
    await user.type(screen.getByLabelText('Palavra-passe'), 'senha-correta')
    await user.click(screen.getByRole('button', { name: 'Entrar' }))

    await waitFor(() => expect(screen.getByText('Área autenticada')).toBeInTheDocument())
    expect(authService.me).toHaveBeenCalledTimes(2)
  })

  it('returns to a safe protected destination after login', async () => {
    const authenticatedUser = {
      id: '1',
      email: 'ana@example.com',
      full_name: 'Ana',
      role: 'patient' as const,
      clinic_id: 'c1',
    }
    vi.mocked(authService.login).mockResolvedValue(authenticatedUser)
    vi.mocked(authService.me).mockRejectedValue(new ApiError(401, 'unauthorized'))
    const user = userEvent.setup()
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={[{ pathname: '/login', state: { from: '/app/consultas?dia=hoje' } }]}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/app/consultas" element={<div>Consultas recuperadas</div>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )
    await user.type(screen.getByLabelText('Email'), 'ana@example.com')
    await user.type(screen.getByLabelText('Palavra-passe'), 'senha-correta')
    vi.mocked(authService.me).mockResolvedValue(authenticatedUser)
    await user.click(screen.getByRole('button', { name: 'Entrar' }))
    expect(await screen.findByText('Consultas recuperadas')).toBeInTheDocument()
  })

  it('shows a network error without fabricating a session', async () => {
    const { NetworkError } = await import('../../lib/apiClient')
    vi.mocked(authService.login).mockRejectedValue(new NetworkError())
    const user = userEvent.setup()
    renderLoginPage()

    await user.type(screen.getByLabelText('Email'), 'ana@example.com')
    await user.type(screen.getByLabelText('Palavra-passe'), 'senha-correta')
    await user.click(screen.getByRole('button', { name: 'Entrar' }))
    expect(await screen.findByText(/Sem ligação ao servidor/)).toBeInTheDocument()
  })

  it('rejects an external return destination and falls back to /app', async () => {
    vi.mocked(authService.me).mockResolvedValue({
      id: '1',
      email: 'ana@example.com',
      full_name: 'Ana',
      role: 'patient',
      clinic_id: 'c1',
    })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[{ pathname: '/login', state: { from: 'https://evil.example' } }]}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/app" element={<div>Área autenticada segura</div>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    expect(await screen.findByText('Área autenticada segura')).toBeInTheDocument()
  })
})
