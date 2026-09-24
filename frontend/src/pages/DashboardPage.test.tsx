import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAppointments, usePatients, useStaff, useUpcomingAppointments } from '../hooks/useClinicData'
import { useOwnClinicName } from '../hooks/useOwnClinicName'
import { useSession } from '../hooks/useSession'
import type { AppointmentPublic, UserPublic } from '../types/api'
import { DashboardPage } from './DashboardPage'

vi.mock('../hooks/useSession')
vi.mock('../hooks/useClinicData')
vi.mock('../hooks/useOwnClinicName')

const patient: UserPublic = {
  id: 'user-1',
  email: 'ana@example.com',
  full_name: 'Ana Silva',
  role: 'patient',
  clinic_id: 'clinic-1',
}

function appointment(overrides: Partial<AppointmentPublic> = {}): AppointmentPublic {
  return {
    id: 'appointment-1',
    clinic_id: 'clinic-1',
    patient_id: 'patient-1',
    staff_id: 'staff-1',
    scheduled_at: new Date(Date.now() + 86_400_000).toISOString(),
    duration_minutes: 30,
    status: 'scheduled',
    reason: 'Consulta de rotina',
    ...overrides,
  }
}

function queryResult<T>(data: T | undefined, options: { loading?: boolean; error?: unknown } = {}) {
  return {
    data,
    isLoading: options.loading ?? false,
    isError: options.error !== undefined,
    error: options.error ?? null,
    refetch: vi.fn(),
  }
}

function renderDashboard() {
  return render(
    <MemoryRouter initialEntries={['/app']}>
      <Routes>
        <Route path="/app" element={<DashboardPage />} />
        <Route path="/app/consultas" element={<div>Destino consultas</div>} />
        <Route path="/app/perfil" element={<div>Destino perfil</div>} />
        <Route path="/app/pacientes" element={<div>Destino pacientes</div>} />
        <Route path="/app/equipa" element={<div>Destino equipa</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.mocked(useSession).mockReturnValue({ user: patient } as ReturnType<typeof useSession>)
  vi.mocked(useAppointments).mockReturnValue(
    queryResult([appointment()]) as unknown as ReturnType<typeof useAppointments>,
  )
  vi.mocked(useUpcomingAppointments).mockReturnValue(
    queryResult([appointment()]) as unknown as ReturnType<typeof useUpcomingAppointments>,
  )
  vi.mocked(usePatients).mockReturnValue(
    queryResult([{ id: 'patient-1', clinic_id: 'clinic-1', full_name: 'Maria Costa', birth_date: null, phone: null }]) as unknown as ReturnType<
      typeof usePatients
    >,
  )
  vi.mocked(useStaff).mockReturnValue(
    queryResult([{ id: 'staff-1', clinic_id: 'clinic-1', full_name: 'Dr. Rui', staff_role: 'doctor', specialty: null }]) as unknown as ReturnType<
      typeof useStaff
    >,
  )
  vi.mocked(useOwnClinicName).mockReturnValue('Clínica Central')
})

describe('DashboardPage', () => {
  it('shows the patient dashboard with scoped appointment details and patient actions', () => {
    renderDashboard()

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Ana Silva')
    expect(screen.getByText('Dr. Rui · 30 min')).toBeInTheDocument()
    expect(screen.getByText('Consulta de rotina')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Perfil/ })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Equipa/ })).not.toBeInTheDocument()

    const startDate = vi.mocked(useUpcomingAppointments).mock.calls[0][0]
    expect(new Date(startDate).toString()).not.toBe('Invalid Date')
  })

  it('shows a stable loading state and an honest empty state', () => {
    vi.mocked(useUpcomingAppointments).mockReturnValue(
      queryResult(undefined, { loading: true }) as unknown as ReturnType<typeof useUpcomingAppointments>,
    )
    const { rerender } = renderDashboard()
    expect(screen.getByRole('status', { name: 'A carregar consultas' })).toBeInTheDocument()

    vi.mocked(useUpcomingAppointments).mockReturnValue(
      queryResult([]) as unknown as ReturnType<typeof useUpcomingAppointments>,
    )
    rerender(
      <MemoryRouter initialEntries={['/app']}>
        <DashboardPage />
      </MemoryRouter>,
    )
    expect(screen.getByText('Sem consultas futuras')).toBeInTheDocument()
  })

  it('keeps the patient dashboard usable when appointments fail and retries', async () => {
    const retry = vi.fn()
    vi.mocked(useUpcomingAppointments).mockReturnValue({
      ...queryResult(undefined, { error: new Error('private backend detail') }),
      refetch: retry,
    } as unknown as ReturnType<typeof useUpcomingAppointments>)
    const user = userEvent.setup()
    renderDashboard()

    expect(screen.getByRole('alert')).toHaveTextContent('Ocorreu um erro inesperado')
    expect(screen.queryByText('private backend detail')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Tentar novamente' }))
    expect(retry).toHaveBeenCalledOnce()
    expect(screen.getByRole('link', { name: /Perfil/ })).toBeInTheDocument()
  })

  it('shows staff appointment information and only staff quick actions', () => {
    vi.mocked(useSession).mockReturnValue({ user: { ...patient, role: 'staff' } } as ReturnType<typeof useSession>)
    renderDashboard()

    expect(screen.getAllByText('Maria Costa · 30 min').length).toBeGreaterThan(0)
    expect(screen.getByRole('link', { name: /Pacientes/ })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Perfil/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Equipa/ })).not.toBeInTheDocument()
  })

  it('shows independent staff empty and error states without hiding navigation', () => {
    vi.mocked(useSession).mockReturnValue({ user: { ...patient, role: 'staff' } } as ReturnType<typeof useSession>)
    vi.mocked(useAppointments).mockReturnValue(queryResult([]) as unknown as ReturnType<typeof useAppointments>)
    vi.mocked(useUpcomingAppointments).mockReturnValue(
      queryResult(undefined, { error: new Error('failure') }) as unknown as ReturnType<typeof useUpcomingAppointments>,
    )
    renderDashboard()

    expect(screen.getByText('Sem consultas hoje')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Pacientes/ })).toBeInTheDocument()
  })

  it('shows clinic context and the administrator-only team action', () => {
    vi.mocked(useSession).mockReturnValue({ user: { ...patient, role: 'clinic_admin' } } as ReturnType<typeof useSession>)
    renderDashboard()

    expect(screen.getByText(/Clínica Central/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Equipa/ })).toBeInTheDocument()
    expect(screen.getAllByText('Maria Costa · 30 min').length).toBeGreaterThan(0)
  })

  it('navigates the administrator to team management', async () => {
    vi.mocked(useSession).mockReturnValue({ user: { ...patient, role: 'clinic_admin' } } as ReturnType<typeof useSession>)
    const user = userEvent.setup()
    renderDashboard()
    await user.click(screen.getByRole('link', { name: /Equipa/ }))
    expect(screen.getByText('Destino equipa')).toBeInTheDocument()
  })

  it('navigates quick actions internally', async () => {
    const user = userEvent.setup()
    renderDashboard()
    await user.click(screen.getByRole('link', { name: /Perfil/ }))
    expect(screen.getByText('Destino perfil')).toBeInTheDocument()
  })
})
