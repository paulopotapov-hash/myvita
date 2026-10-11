import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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

    const user = userEvent.setup()
    const accountButton = await screen.findByRole('button', { name: 'Menu da conta' })
    for (const name of ['Início', 'Consultas', 'Mensagens', 'Resultados', 'Documentos', 'Dados clínicos', 'Notificações']) {
      expect(screen.getAllByRole('link', { name }).length).toBeGreaterThan(0)
    }
    // Identity, profile and security live in the avatar menu.
    await user.click(accountButton)
    expect(screen.getByText('Área do paciente')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Perfil' })).toHaveAttribute('href', '/patient/perfil')
    expect(screen.getByRole('link', { name: 'Segurança' })).toHaveAttribute('href', '/patient/seguranca')
    expect(screen.queryByRole('link', { name: 'Pacientes' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Equipa' })).not.toBeInTheDocument()
  })

  it('gives the patient shell the same keyboard and screen-reader affordances as the staff shell', async () => {
    vi.mocked(authService.me).mockResolvedValue({
      id: '1', email: 'ana@example.com', full_name: 'Ana', role: 'patient',
      clinic_id: 'c1', staff_role: null, patient_id: 'p1',
    })
    const user = userEvent.setup()
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/patient']}>
          <Routes>
            <Route path="/patient" element={<PatientLayout />}>
              <Route index element={<div>Dashboard</div>} />
              <Route path="consultas" element={<div>As minhas consultas</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    await screen.findByRole('button', { name: 'Menu da conta' })
    expect(document.title).toBe('Início · myVita')
    await user.tab()
    expect(screen.getByRole('link', { name: 'Saltar para o conteúdo' })).toHaveFocus()
    await user.keyboard('{Enter}')
    expect(screen.getByRole('main')).toHaveFocus()

    const toggle = screen.getByRole('button', { name: 'Menu de navegação' })
    await user.click(toggle)
    expect(document.getElementById(toggle.getAttribute('aria-controls') ?? '')).not.toBeNull()
    await user.keyboard('{Escape}')
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(toggle).toHaveFocus()

    await user.click(screen.getAllByRole('link', { name: 'Consultas' })[0])
    expect(await screen.findByText('As minhas consultas')).toBeInTheDocument()
    expect(screen.getByRole('main')).toHaveFocus()
    expect(document.title).toBe('As minhas consultas · myVita')
  })
})
