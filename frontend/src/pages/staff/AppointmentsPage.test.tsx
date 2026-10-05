import { act, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../lib/apiClient'
import { AppointmentsPage } from './AppointmentsPage'

const { appointmentState, cancelMutate, createMutate, updateMutate, patientSearchQuery } = vi.hoisted(() => ({
  appointmentState: { rows: [] as Array<Record<string, unknown>> },
  cancelMutate: vi.fn(),
  createMutate: vi.fn(),
  updateMutate: vi.fn(),
  patientSearchQuery: vi.fn(),
}))

vi.mock('../../hooks/useSession', () => ({
  useSession: () => ({
    user: { id: 'doctor-1', email: 'doctor@example.pt', full_name: 'Doctor', role: 'staff', clinic_id: 'clinic-1', staff_role: 'doctor', patient_id: null },
  }),
}))

vi.mock('../../hooks/useClinicData', () => ({
  useAppointmentsPage: () => ({ data: { items: appointmentState.rows, total: appointmentState.rows.length }, isLoading: false, isError: false, isFetching: false, refetch: vi.fn() }),
  usePatients: () => ({ data: [{ id: 'patient-1', full_name: 'Ana' }], isLoading: false, isError: false }),
  usePatientSearch: (...args: unknown[]) => patientSearchQuery(...args),
  useStaff: () => ({ data: [{ id: 'staff-1', full_name: 'Dr. Rui' }], isLoading: false, isError: false }),
  useCreateAppointment: () => ({ mutate: createMutate, isPending: false }),
  useUpdateAppointment: () => ({ mutate: updateMutate, isPending: false }),
  useCancelAppointment: () => ({ mutate: cancelMutate, isPending: false }),
}))

function renderPage() {
  return render(<MemoryRouter><AppointmentsPage /></MemoryRouter>)
}

async function fillAndSubmit() {
  const user = userEvent.setup()
  renderPage()
  await user.type(screen.getByLabelText('Pesquisar paciente'), 'Ana')
  await user.selectOptions(screen.getByLabelText('Paciente'), 'patient-1')
  await user.selectOptions(screen.getByLabelText('Profissional'), 'staff-1')
  fireEvent.change(screen.getByLabelText('Data e hora'), { target: { value: '2026-10-20T10:30' } })
  await user.type(screen.getByLabelText('Motivo (opcional)'), 'Consulta anual')
  await user.click(screen.getByRole('button', { name: 'Marcar consulta' }))
}

describe('AppointmentsPage clinical workflow', () => {
  beforeEach(() => {
    appointmentState.rows = []
    patientSearchQuery.mockImplementation((_search: string, page: number) => ({
      data: {
        items: page === 1
          ? [{ id: 'patient-1', full_name: 'Ana' }]
          : [{ id: 'patient-21', full_name: 'Paciente página 2' }],
        total: 21,
      },
      isLoading: false,
      isError: false,
      isFetching: false,
      error: null,
    }))
    createMutate.mockReset()
    updateMutate.mockReset()
    cancelMutate.mockReset()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
  })

  it('paginates patient search results and preserves the selected patient when changing pages', async () => {
    const user = userEvent.setup()
    renderPage()
    const search = screen.getByLabelText('Pesquisar paciente')
    await user.type(search, 'Ana')
    await user.selectOptions(screen.getByLabelText('Paciente'), 'patient-1')
    expect(screen.getByText('Paciente selecionado: Ana')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Seguinte' }))
    expect(patientSearchQuery).toHaveBeenLastCalledWith('Ana', 2, 10)
    expect(screen.getByRole('option', { name: 'Ana' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Paciente página 2' })).toBeInTheDocument()
  })

  it('submits the exact appointment create contract including duration and ISO time', async () => {
    await fillAndSubmit()
    expect(createMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        patient_id: 'patient-1',
        staff_id: 'staff-1',
        duration_minutes: 30,
        reason: 'Consulta anual',
        scheduled_at: new Date('2026-10-20T10:30').toISOString(),
      }),
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
    )
  })

  it('exposes only the status actions allowed for each backend state', async () => {
    appointmentState.rows = [{
      id: 'appointment-1', clinic_id: 'clinic-1', patient_id: 'patient-1', staff_id: 'staff-1',
      scheduled_at: '2026-10-20T10:30:00Z', duration_minutes: 30, status: 'scheduled', reason: null,
    }]
    const user = userEvent.setup()
    const rendered = renderPage()
    await user.click(screen.getByRole('button', { name: 'Detalhes' }))
    expect(screen.getByRole('button', { name: 'Cancelar consulta' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Confirmar' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Concluir' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Marcar falta' })).not.toBeInTheDocument()

    appointmentState.rows[0].status = 'confirmed'
    rendered.rerender(<MemoryRouter><AppointmentsPage /></MemoryRouter>)
    await user.click(screen.getByRole('button', { name: 'Detalhes' }))
    expect(screen.getByRole('button', { name: 'Cancelar consulta' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Confirmar' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Concluir' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Marcar falta' })).toBeInTheDocument()
  })

  it('sends the explicit backend status transition after confirmation', async () => {
    appointmentState.rows = [{
      id: 'appointment-1', clinic_id: 'clinic-1', patient_id: 'patient-1', staff_id: 'staff-1',
      scheduled_at: '2026-10-20T10:30:00Z', duration_minutes: 30, status: 'scheduled', reason: null,
    }]
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole('button', { name: 'Detalhes' }))
    await user.click(screen.getByRole('button', { name: 'Confirmar' }))
    const confirmation = screen.getByRole('alertdialog', { name: 'Confirmar consulta' })
    await user.click(within(confirmation).getByRole('button', { name: 'Confirmar' }))
    expect(updateMutate).toHaveBeenCalledWith(
      { id: 'appointment-1', payload: { status: 'confirmed' } },
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
    )
  })

  it('shows a backend 409 conflict instead of swallowing it', async () => {
    await fillAndSubmit()
    const options = createMutate.mock.calls.at(-1)?.[1] as
      | { onError: (error: unknown) => void }
      | undefined
    expect(options).toBeDefined()
    act(() => {
      options?.onError(
        new ApiError(409, 'Já existe uma consulta sobreposta.', {
          detail: 'Já existe uma consulta sobreposta.',
        }),
      )
    })
    expect(await screen.findByRole('alert')).toHaveTextContent('Já existe uma consulta sobreposta.')
  })

  it('updates and explicitly cancels an existing appointment', async () => {
    appointmentState.rows = [{
      id: 'appointment-1', clinic_id: 'clinic-1', patient_id: 'patient-1', staff_id: 'staff-1',
      scheduled_at: '2026-10-20T10:30:00Z', duration_minutes: 30, status: 'scheduled', reason: 'Consulta anual',
    }]
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole('button', { name: 'Detalhes' }))
    const dialog = screen.getByRole('dialog')
    const duration = dialog.querySelector<HTMLInputElement>('input[type="number"]')
    expect(duration).not.toBeNull()
    await user.clear(duration!)
    await user.type(duration!, '45')
    await user.click(screen.getByRole('button', { name: 'Guardar alterações' }))
    expect(updateMutate).toHaveBeenCalledWith(
      {
        id: 'appointment-1',
        payload: {
          scheduled_at: new Date('2026-10-20T10:30:00Z').toISOString(),
          duration_minutes: 45,
          reason: 'Consulta anual',
        },
      },
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
    )

    await user.click(screen.getByRole('button', { name: 'Cancelar consulta' }))
    const cancelDialog = screen.getByRole('alertdialog', { name: 'Cancelar consulta' })
    await user.click(within(cancelDialog).getByRole('button', { name: 'Cancelar consulta' }))
    expect(cancelMutate).toHaveBeenCalledWith(
      'appointment-1',
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
    )
    const cancelOptions = cancelMutate.mock.calls.at(-1)?.[1] as { onSuccess: () => void }
    act(() => cancelOptions.onSuccess())
    expect(await screen.findByRole('status')).toHaveTextContent('Consulta cancelada.')
  })
})
