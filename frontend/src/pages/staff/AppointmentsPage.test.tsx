import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../lib/apiClient'
import { AppointmentsPage } from './AppointmentsPage'

const { appointmentState, cancelMutate, createMutate, updateMutate } = vi.hoisted(() => ({
  appointmentState: { rows: [] as Array<Record<string, unknown>> },
  cancelMutate: vi.fn(),
  createMutate: vi.fn(),
  updateMutate: vi.fn(),
}))

vi.mock('../../hooks/useSession', () => ({
  useSession: () => ({
    user: { id: 'admin-1', email: 'admin@example.pt', full_name: 'Admin', role: 'clinic_admin', clinic_id: 'clinic-1', staff_role: null, patient_id: null },
  }),
}))

vi.mock('../../hooks/useClinicData', () => ({
  useAppointments: () => ({ data: appointmentState.rows, isLoading: false, isError: false, refetch: vi.fn() }),
  usePatients: () => ({ data: [{ id: 'patient-1', full_name: 'Ana' }], isLoading: false, isError: false }),
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
  await user.selectOptions(screen.getByLabelText('Paciente'), 'patient-1')
  await user.selectOptions(screen.getByLabelText('Profissional'), 'staff-1')
  fireEvent.change(screen.getByLabelText('Data e hora'), { target: { value: '2026-10-20T10:30' } })
  await user.type(screen.getByLabelText('Motivo (opcional)'), 'Consulta anual')
  await user.click(screen.getByRole('button', { name: 'Marcar consulta' }))
}

describe('AppointmentsPage clinical workflow', () => {
  beforeEach(() => {
    appointmentState.rows = []
    createMutate.mockReset()
    updateMutate.mockReset()
    cancelMutate.mockReset()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
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
      { id: 'appointment-1', payload: { duration_minutes: 45, reason: 'Consulta anual' } },
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
    )

    await user.click(screen.getByRole('button', { name: 'Cancelar consulta' }))
    expect(window.confirm).toHaveBeenCalledWith('Cancelar esta consulta?')
    expect(cancelMutate).toHaveBeenCalledWith(
      'appointment-1',
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
    )
  })
})
