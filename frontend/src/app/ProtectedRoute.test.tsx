import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { ProtectedRoute } from './ProtectedRoute'
import { ApiError } from '../lib/apiClient'
import { authService } from '../services/auth'

vi.mock('../services/auth')

function renderProtected() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/app']}>
        <Routes>
          <Route path="/login" element={<div>Página de login</div>} />
          <Route
            path="/app"
            element={
              <ProtectedRoute>
                <div>Conteúdo protegido</div>
              </ProtectedRoute>
            }
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('ProtectedRoute', () => {
  it('shows a loading state while checking the session', () => {
    vi.mocked(authService.me).mockReturnValue(new Promise(() => {})) // never resolves
    renderProtected()
    expect(screen.getByRole('status')).toBeInTheDocument()
  })

  it('redirects to /login when the session check returns 401', async () => {
    vi.mocked(authService.me).mockRejectedValue(new ApiError(401, 'unauthorized'))
    renderProtected()
    await waitFor(() => expect(screen.getByText('Página de login')).toBeInTheDocument())
  })

  it('renders the protected content once authenticated', async () => {
    vi.mocked(authService.me).mockResolvedValue({
      id: '1',
      email: 'a@b.pt',
      full_name: 'Ana',
      role: 'patient',
      clinic_id: 'c1',
    })
    renderProtected()
    await waitFor(() => expect(screen.getByText('Conteúdo protegido')).toBeInTheDocument())
  })

  it('shows a retryable error state on a genuine server error (never a redirect loop to /login)', async () => {
    vi.mocked(authService.me).mockRejectedValue(new ApiError(500, 'Erro interno do servidor.'))
    renderProtected()
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(screen.queryByText('Página de login')).not.toBeInTheDocument()
  })
})
