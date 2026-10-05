import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { AppLayout } from './AppLayout'
import { authService } from '../services/auth'
import { NetworkError } from '../lib/apiClient'
import type { UserPublic } from '../types/api'

vi.mock('../services/auth')
const { logoutMutate, logoutState } = vi.hoisted(() => ({ logoutMutate: vi.fn(), logoutState: { isPending: false, isError: false, error: null as Error | null } }))
vi.mock('../hooks/useAuthMutations', () => ({
  useLogout: () => ({ mutate: logoutMutate, isPending: logoutState.isPending, isError: logoutState.isError, error: logoutState.error }),
}))

function renderLayoutAsRole(role: UserPublic['role']) {
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
      <MemoryRouter initialEntries={['/app']}>
        <Routes>
          <Route path="/app" element={<AppLayout />}>
            <Route index element={<div>Dashboard</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('AppLayout navigation', () => {
  it('starts the server-backed logout flow from the staff shell', async () => {
    const user = userEvent.setup()
    renderLayoutAsRole('staff')
    await user.click(await screen.findByRole('button', { name: 'Sair' }))
    expect(logoutMutate).toHaveBeenCalledOnce()
  })

  it('explains logout failure and offers a retry without pretending the session ended', async () => {
    logoutState.isError = true
    logoutState.error = new NetworkError()
    const user = userEvent.setup()
    renderLayoutAsRole('staff')
    expect(await screen.findByRole('alert')).toHaveTextContent('Sem ligação ao servidor')
    expect(screen.getByRole('alert')).toHaveTextContent('A sessão continua ativa')
    await user.click(screen.getByRole('button', { name: 'Tentar sair novamente' }))
    expect(logoutMutate).toHaveBeenCalledOnce()
    logoutState.isError = false
    logoutState.error = null
  })

  it('shows admin-only "Equipa" link only for clinic_admin', async () => {
    renderLayoutAsRole('clinic_admin')
    await waitFor(() => expect(screen.getByText('Ana')).toBeInTheDocument())
    expect(screen.getAllByRole('link', { name: 'Equipa' }).length).toBeGreaterThan(0)
  })

  it('does not show the admin "Equipa" link for staff', async () => {
    renderLayoutAsRole('staff')
    await waitFor(() => expect(screen.getByText('Ana')).toBeInTheDocument())
    expect(screen.queryAllByRole('link', { name: 'Equipa' })).toHaveLength(0)
    expect(screen.getAllByRole('link', { name: 'Pacientes' }).length).toBeGreaterThan(0)
  })
})
