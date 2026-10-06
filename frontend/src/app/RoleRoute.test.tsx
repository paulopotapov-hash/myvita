import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { RoleRoute } from './RoleRoute'
import { authService } from '../services/auth'
import type { UserPublic } from '../types/api'

vi.mock('../services/auth')

function renderAsRole(role: UserPublic['role']) {
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
      <MemoryRouter initialEntries={['/app/equipa']}>
        <Routes>
          <Route path="/app" element={<div>Dashboard</div>} />
          <Route
            path="/app/equipa"
            element={
              <RoleRoute allow={['clinic_admin']}>
                <div>Gestão de equipa</div>
              </RoleRoute>
            }
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('RoleRoute', () => {
  it('renders the page when the role is allowed', async () => {
    renderAsRole('clinic_admin')
    await waitFor(() => expect(screen.getByText('Gestão de equipa')).toBeInTheDocument())
  })

  it('redirects away when the role is not allowed (patient hitting an admin-only page)', async () => {
    renderAsRole('patient')
    await waitFor(() => expect(screen.getByText('Dashboard')).toBeInTheDocument())
    expect(screen.queryByText('Gestão de equipa')).not.toBeInTheDocument()
  })

  it('redirects away for staff too (only clinic_admin is allowed here)', async () => {
    renderAsRole('staff')
    await waitFor(() => expect(screen.getByText('Dashboard')).toBeInTheDocument())
  })
})
