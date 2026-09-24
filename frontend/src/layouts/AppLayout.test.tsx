import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AppLayout } from './AppLayout'
import { authService } from '../services/auth'
import type { UserPublic } from '../types/api'

vi.mock('../services/auth')
const logoutState = vi.hoisted(() => ({
  mutate: vi.fn(),
  isPending: false,
  isError: false,
  error: null as unknown,
}))
vi.mock('../hooks/useAuthMutations', () => ({
  useLogout: () => logoutState,
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
          <Route path="/login" element={<div>Página de login</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  logoutState.mutate.mockReset()
  logoutState.isPending = false
  logoutState.isError = false
  logoutState.error = null
})

describe('AppLayout navigation', () => {
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

  it('navigates to login after the server confirms logout', async () => {
    logoutState.mutate.mockImplementation((_variables, options) => {
      ;(options as { onSuccess?: () => void } | undefined)?.onSuccess?.()
    })
    const user = userEvent.setup()
    renderLayoutAsRole('patient')
    await user.click(await screen.findByRole('button', { name: 'Sair' }))
    expect(screen.getByText('Página de login')).toBeInTheDocument()
  })

  it('shows a logout failure and lets the user retry', async () => {
    const { NetworkError } = await import('../lib/apiClient')
    logoutState.isError = true
    logoutState.error = new NetworkError()
    const user = userEvent.setup()
    renderLayoutAsRole('patient')

    expect(await screen.findByRole('alert')).toHaveTextContent('Sem ligação ao servidor')
    await user.click(screen.getByRole('button', { name: 'Sair' }))
    await user.click(screen.getByRole('button', { name: 'Sair' }))
    expect(logoutState.mutate).toHaveBeenCalledTimes(2)
    expect(screen.getByText('Dashboard')).toBeInTheDocument()
  })
})
