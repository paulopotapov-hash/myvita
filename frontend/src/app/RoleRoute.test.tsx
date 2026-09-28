import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { RoleRoute } from './RoleRoute'
import { authService } from '../services/auth'
import type { UserPublic, UserRole } from '../types/api'

vi.mock('../services/auth')

function renderRoute(role: UserPublic['role'], initialPath: string, allow: UserRole[]) {
  vi.mocked(authService.me).mockResolvedValue({
    id: '1',
    email: 'a@b.pt',
    full_name: 'Ana',
    role,
    clinic_id: 'c1',
    staff_role: role === 'staff' ? 'doctor' : null,
    patient_id: role === 'patient' ? 'p1' : null,
  })
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/app" element={<div>Staff home</div>} />
          <Route path="/patient" element={<div>Patient home</div>} />
          <Route
            path={initialPath}
            element={
              <RoleRoute allow={allow}>
                <div>Allowed page</div>
              </RoleRoute>
            }
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('RoleRoute', () => {
  it('renders a directly opened page when the role is allowed', async () => {
    renderRoute('clinic_admin', '/app/equipa', ['clinic_admin'])
    await waitFor(() => expect(screen.getByText('Allowed page')).toBeInTheDocument())
  })

  it('redirects a patient opening /app/* to /patient without looping', async () => {
    renderRoute('patient', '/app/equipa', ['clinic_admin'])
    await waitFor(() => expect(screen.getByText('Patient home')).toBeInTheDocument())
  })

  it.each(['staff', 'clinic_admin'] as const)('redirects %s opening /patient/* to /app', async (role) => {
    renderRoute(role, '/patient/saude', ['patient'])
    await waitFor(() => expect(screen.getByText('Staff home')).toBeInTheDocument())
  })

  it('keeps staff out of the admin-only team route', async () => {
    renderRoute('staff', '/app/equipa', ['clinic_admin'])
    await waitFor(() => expect(screen.getByText('Staff home')).toBeInTheDocument())
  })
})
