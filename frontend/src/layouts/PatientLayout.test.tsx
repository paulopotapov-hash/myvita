import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { PatientLayout } from './PatientLayout'
import { authService } from '../services/auth'

vi.mock('../services/auth')
vi.mock('../hooks/useAuthMutations', () => ({
  useLogout: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
}))

describe('PatientLayout navigation', () => {
  it('provides the dedicated patient navigation and identity', async () => {
    vi.mocked(authService.me).mockResolvedValue({
      id: '1', email: 'ana@example.com', full_name: 'Ana', role: 'patient',
      clinic_id: 'c1', staff_role: null, patient_id: 'p1',
    })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/patient']}>
          <Routes>
            <Route path="/patient" element={<PatientLayout />}>
              <Route index element={<div>Dashboard</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    await waitFor(() => expect(screen.getByText('Ana')).toBeInTheDocument())
    expect(screen.getByText('Área do paciente')).toBeInTheDocument()
    for (const name of ['Início', 'Consultas', 'Dados clínicos', 'Perfil', 'Notificações']) {
      expect(screen.getAllByRole('link', { name }).length).toBeGreaterThan(0)
    }
    expect(screen.queryByRole('link', { name: 'Pacientes' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Equipa' })).not.toBeInTheDocument()
  })
})
