import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { RootRedirect } from './RootRedirect'
import { ApiError } from '../lib/apiClient'
import { authService } from '../services/auth'
import type { UserRole } from '../types/api'

vi.mock('../services/auth')

function renderRoot(role?: UserRole) {
  if (role) {
    vi.mocked(authService.me).mockResolvedValue({
      id: '1', email: 'ana@example.com', full_name: 'Ana', role,
      clinic_id: 'c1', staff_role: role === 'staff' ? 'doctor' : null,
      patient_id: role === 'patient' ? 'p1' : null,
    })
  } else {
    vi.mocked(authService.me).mockRejectedValue(new ApiError(401, 'unauthorized'))
  }
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route path="/" element={<RootRedirect />} />
          <Route path="/login" element={<div>Login</div>} />
          <Route path="/patient" element={<div>Patient home</div>} />
          <Route path="/app" element={<div>Staff home</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('RootRedirect', () => {
  it('redirects an anonymous user to /login', async () => {
    renderRoot()
    await waitFor(() => expect(screen.getByText('Login')).toBeInTheDocument())
  })

  it('redirects a patient to /patient', async () => {
    renderRoot('patient')
    await waitFor(() => expect(screen.getByText('Patient home')).toBeInTheDocument())
  })

  it.each(['staff', 'clinic_admin'] as const)('redirects %s to /app', async (role) => {
    renderRoot(role)
    await waitFor(() => expect(screen.getByText('Staff home')).toBeInTheDocument())
  })
})
