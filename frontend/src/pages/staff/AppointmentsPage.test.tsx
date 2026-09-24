import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  useAppointment,
  useAppointments,
  useCancelAppointment,
  useCreateAppointment,
  usePatients,
  useStaff,
  useUpdateAppointment,
} from '../../hooks/useClinicData'
import { useSession } from '../../hooks/useSession'
import type { AppointmentPublic, UserPublic } from '../../types/api'
import { AppointmentDetailPage, AppointmentsPage } from './AppointmentsPage'

vi.mock('../../hooks/useClinicData')
vi.mock('../../hooks/useSession')

const patientUser: UserPublic = {
  id: 'user-1',
  email: 'ana@example.com',
  full_name: 'Ana',
  role: 'patient',
  clinic_id: 'clinic-1',
}

function appointment(overrides: Partial<AppointmentPublic> = {}): AppointmentPublic {
  return {
    id: 'appointment-1',
    clinic_id: 'clinic-1',
    patient_id: 'patient-1',
    staff_id: 'staff-1',
    scheduled_at: '2030-05-20T09:30:00Z',
    duration_minutes: 30,
    status: 'scheduled',
    reason: 'Consulta anual',
    ...overrides,
  }
}

function queryResult<T>(data: T | undefined, options: { loading?: boolean; error?: unknown } = {}) {
  return {
    data,
    isLoading: options.loading ?? false,
    isFetching: options.loading ?? false,
    isError: options.error !== undefined,
    error: options.error ?? null,
    refetch: vi.fn(),
  }
}

const createMutation = { mutate: vi.fn(), isPending: false }
const updateMutation = { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }
const cancelMutation = { mutate: vi.fn(), isPending: false }

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(useSession).mockReturnValue({ user: patientUser } as ReturnType<typeof useSession>)
  vi.mocked(useAppointments).mockReturnValue(
    queryResult([appointment()]) as unknown as ReturnType<typeof useAppointments>,
  )
  vi.mocked(useAppointment).mockReturnValue(
    queryResult(appointment()) as unknown as ReturnType<typeof useAppointment>,
  )
  vi.mocked(usePatients).mockReturnValue(
    queryResult([{ id: 'patient-1', full_name: 'Ana', clinic_id: 'clinic-1', birth_date: null, phone: null }]) as unknown as ReturnType<
      typeof usePatients
    >,
  )
  vi.mocked(useStaff).mockReturnValue(
    queryResult([{ id: 'staff-1', full_name: 'Dra. Maria', clinic_id: 'clinic-1', staff_role: 'doctor', specialty: null }]) as unknown as ReturnType<
      typeof useStaff
    >,
  )
  vi.mocked(useCreateAppointment).mockReturnValue(createMutation as unknown as ReturnType<typeof useCreateAppointment>)
  vi.mocked(useUpdateAppointment).mockReturnValue(updateMutation as unknown as ReturnType<typeof useUpdateAppointment>)
  vi.mocked(useCancelAppointment).mockReturnValue(cancelMutation as unknown as ReturnType<typeof useCancelAppointment>)
})

function renderList(initialEntry = '/app/consultas') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/app/consultas" element={<AppointmentsPage />} />
        <Route path="/app/consultas/:appointmentId" element={<div>Detalhe navegado</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

function renderDetail() {
  return render(
    <MemoryRouter initialEntries={['/app/consultas/appointment-1']}>
      <Routes>
        <Route path="/app/consultas/:appointmentId" element={<AppointmentDetailPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('AppointmentsPage', () => {
  it('renders the patient-scoped list without clinic-wide selectors', async () => {
    const user = userEvent.setup()
    renderList()

    expect(screen.getByText('As tuas consultas')).toBeInTheDocument()
    expect(screen.getByText(/Com Dra. Maria/)).toBeInTheDocument()
    expect(screen.queryByLabelText('Paciente')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Profissional')).not.toBeInTheDocument()
    await user.click(screen.getByRole('link', { name: 'Ver detalhe' }))
    expect(screen.getByText('Detalhe navegado')).toBeInTheDocument()
  })

  it('applies authorized server filters and clears them', async () => {
    vi.mocked(useSession).mockReturnValue({ user: { ...patientUser, role: 'staff' } } as ReturnType<typeof useSession>)
    const user = userEvent.setup()
    renderList('/app/consultas?status=confirmed&patient_id=patient-1')

    expect(screen.getByLabelText('Paciente')).toHaveValue('patient-1')
    expect(screen.getByLabelText('Estado')).toHaveValue('confirmed')
    await user.selectOptions(screen.getByLabelText('Profissional'), 'staff-1')
    await waitFor(() =>
      expect(vi.mocked(useAppointments).mock.calls.at(-1)?.[0]).toMatchObject({
        patient_id: 'patient-1',
        staff_id: 'staff-1',
        status: 'confirmed',
      }),
    )
    await user.click(screen.getByRole('button', { name: 'Limpar filtros' }))
    expect(screen.getByLabelText('Estado')).toHaveValue('')
  })

  it('uses offset pagination without inventing a total', async () => {
    vi.mocked(useAppointments).mockReturnValue(
      queryResult(Array.from({ length: 20 }, (_, index) => appointment({ id: `appointment-${index}` }))) as unknown as ReturnType<
        typeof useAppointments
      >,
    )
    const user = userEvent.setup()
    renderList()
    await user.click(screen.getByRole('button', { name: 'Seguinte' }))
    await waitFor(() => expect(vi.mocked(useAppointments).mock.calls.at(-1)?.[0]?.offset).toBe(20))
    expect(screen.getByText('Página 2')).toBeInTheDocument()
  })

  it('handles loading, empty and error states with retry', async () => {
    vi.mocked(useAppointments).mockReturnValue(
      queryResult(undefined, { loading: true }) as unknown as ReturnType<typeof useAppointments>,
    )
    const view = renderList()
    expect(screen.getByRole('status')).toBeInTheDocument()

    vi.mocked(useAppointments).mockReturnValue(queryResult([]) as unknown as ReturnType<typeof useAppointments>)
    view.rerender(<MemoryRouter initialEntries={['/app/consultas']}><AppointmentsPage /></MemoryRouter>)
    expect(screen.getByText('Sem consultas')).toBeInTheDocument()

    const retry = vi.fn()
    vi.mocked(useAppointments).mockReturnValue({ ...queryResult(undefined, { error: new Error('internal') }), refetch: retry } as unknown as ReturnType<typeof useAppointments>)
    view.rerender(<MemoryRouter initialEntries={['/app/consultas']}><AppointmentsPage /></MemoryRouter>)
    await userEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))
    expect(retry).toHaveBeenCalledOnce()
  })

  it('creates an appointment from validated real form values for authorized staff', async () => {
    vi.mocked(useSession).mockReturnValue({ user: { ...patientUser, role: 'clinic_admin' } } as ReturnType<typeof useSession>)
    const user = userEvent.setup()
    renderList()
    await user.click(screen.getByRole('button', { name: 'Marcar consulta' }))
    const dialog = screen.getByRole('dialog')
    await user.selectOptions(within(dialog).getByLabelText('Paciente'), 'patient-1')
    await user.selectOptions(within(dialog).getByLabelText('Profissional'), 'staff-1')
    await user.type(within(dialog).getByLabelText('Data e hora (hora local)'), '2030-05-20T10:30')
    await user.click(within(dialog).getByRole('button', { name: 'Marcar consulta' }))

    expect(createMutation.mutate).toHaveBeenCalledWith(
      expect.objectContaining({ patient_id: 'patient-1', staff_id: 'staff-1', duration_minutes: 30 }),
      expect.any(Object),
    )
  })
})

describe('AppointmentDetailPage', () => {
  it('shows permitted detail without exposing internal identifiers and lets a patient cancel', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const user = userEvent.setup()
    renderDetail()

    expect(screen.getByRole('heading', { name: 'Detalhe da consulta' })).toBeInTheDocument()
    expect(screen.getByText('Dra. Maria')).toBeInTheDocument()
    expect(screen.queryByText('appointment-1')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Editar consulta' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Cancelar consulta' }))
    expect(cancelMutation.mutate).toHaveBeenCalledWith('appointment-1', expect.any(Object))
  })

  it('offers only valid staff transitions and validates edits before mutation', async () => {
    vi.mocked(useSession).mockReturnValue({ user: { ...patientUser, role: 'staff' } } as ReturnType<typeof useSession>)
    const user = userEvent.setup()
    renderDetail()

    expect(screen.getByRole('button', { name: 'Confirmar' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Concluir' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Editar consulta' }))
    const duration = screen.getByLabelText('Duração (minutos)')
    await user.clear(duration)
    await user.type(duration, '2')
    await user.click(screen.getByRole('button', { name: 'Guardar alterações' }))
    expect(await screen.findByText('A duração mínima é 5 minutos.')).toBeInTheDocument()
    expect(updateMutation.mutate).not.toHaveBeenCalled()
  })
})
