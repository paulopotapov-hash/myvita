import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { AppLayout } from './AppLayout'
import { authService } from '../services/auth'
import type { UserPublic } from '../types/api'

vi.mock('../services/auth')
const { logoutMutate } = vi.hoisted(() => ({ logoutMutate: vi.fn() }))
vi.mock('../hooks/useAuthMutations', () => ({
  useLogout: () => ({ mutate: logoutMutate, isPending: false }),
}))

function renderLayoutAsRole(role: UserPublic['role']) {
  vi.mocked(authService.me).mockResolvedValue({
    id: '1',
    email: 'a@b.pt',
    full_name: 'Ana',
    role,
    clinic_id: 'c1',
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
  it('starts the server-backed logout flow from the application shell', async () => {
    const user = userEvent.setup()
    renderLayoutAsRole('patient')
    await user.click(await screen.findByRole('button', { name: 'Sair' }))
    expect(logoutMutate).toHaveBeenCalledOnce()
  })

  it('shows patient-only links for the patient role', async () => {
    renderLayoutAsRole('patient')
    await waitFor(() => expect(screen.getByText('Ana')).toBeInTheDocument())
    expect(screen.getAllByRole('link', { name: 'Perfil' }).length).toBeGreaterThan(0)
    expect(screen.getAllByRole('link', { name: 'As minhas consultas' }).length).toBeGreaterThan(0)
    expect(screen.queryAllByRole('link', { name: 'Equipa' })).toHaveLength(0)
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
