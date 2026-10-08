import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Outlet } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import App from './App'
import { ApiError } from './lib/apiClient'
import { authService } from './services/auth'
import type { UserRole } from './types/api'

vi.mock('./services/auth')
vi.mock('./layouts/AppLayout', () => ({ AppLayout: () => <><div>App layout</div><Outlet /></> }))
vi.mock('./layouts/PatientLayout', () => ({ PatientLayout: () => <><div>Patient layout</div><Outlet /></> }))
vi.mock('./pages/auth/LoginPage', () => ({ LoginPage: () => <div>Login page</div> }))
vi.mock('./pages/DashboardPage', () => ({ DashboardPage: () => <div>App dashboard</div> }))
vi.mock('./pages/patient/PatientDashboard', () => ({ PatientDashboard: () => <div>Patient dashboard</div> }))
vi.mock('./pages/patient/PatientProfilePage', () => ({ PatientProfilePage: () => <div>Patient profile</div> }))
vi.mock('./pages/staff/AppointmentsPage', () => ({ AppointmentsPage: () => <div>Appointments</div> }))
vi.mock('./pages/staff/PatientDetailPage', () => ({ PatientDetailPage: () => <div>Patient health</div> }))
vi.mock('./pages/NotificationsPage', () => ({ NotificationsPage: () => <div>Notifications</div> }))
vi.mock('./pages/staff/PatientsPage', () => ({ PatientsPage: () => <div>Patients</div> }))
vi.mock('./pages/admin/StaffManagementPage', () => ({ StaffManagementPage: () => <div>Team</div> }))

function renderPath(path: string, role?: UserRole) {
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
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('role-separated application routes', () => {
  it.each([
    ['/patient', 'Patient dashboard'],
    ['/patient/perfil', 'Patient profile'],
    ['/patient/saude', 'Patient health'],
    ['/patient/consultas', 'Appointments'],
    ['/patient/notificacoes', 'Notifications'],
  ])('allows a patient to navigate directly to %s', async (path, content) => {
    renderPath(path, 'patient')
    await waitFor(() => expect(screen.getByText(content)).toBeInTheDocument())
    expect(screen.getByText('Patient layout')).toBeInTheDocument()
  })

  it.each(['/app/pacientes', '/app/equipa'])('redirects a patient opening %s to /patient', async (path) => {
    renderPath(path, 'patient')
    await waitFor(() => expect(screen.getByText('Patient dashboard')).toBeInTheDocument())
    expect(screen.queryByText('Patients')).not.toBeInTheDocument()
    expect(screen.queryByText('Team')).not.toBeInTheDocument()
  })

  it.each(['staff', 'clinic_admin'] as const)('redirects %s away from /patient/*', async (role) => {
    renderPath('/patient/perfil', role)
    await waitFor(() => expect(screen.getByText('App dashboard')).toBeInTheDocument())
  })

  it('does not grant staff access to /app/equipa', async () => {
    renderPath('/app/equipa', 'staff')
    await waitFor(() => expect(screen.getByText('App dashboard')).toBeInTheDocument())
    expect(screen.queryByText('Team')).not.toBeInTheDocument()
  })

  it('redirects an anonymous direct navigation to login', async () => {
    renderPath('/patient/saude')
    await waitFor(() => expect(screen.getByText('Login page')).toBeInTheDocument())
  })

  it.each(['/registo', '/nova-clinica'])('does not expose the public self-registration route %s', async (path) => {
    renderPath(path)
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Página não encontrada' })).toBeInTheDocument())
  })
})
