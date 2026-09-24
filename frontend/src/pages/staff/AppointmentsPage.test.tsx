import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../lib/apiClient'
import { AppointmentsPage } from './AppointmentsPage'

const { createMutate } = vi.hoisted(() => ({ createMutate: vi.fn() }))

vi.mock('../../hooks/useSession', () => ({
  useSession: () => ({
    user: { id: 'admin-1', email: 'admin@example.pt', full_name: 'Admin', role: 'clinic_admin', clinic_id: 'clinic-1' },
  }),
}))

vi.mock('../../hooks/useClinicData', () => ({
  useAppointments: () => ({ data: [], isLoading: false, isError: false, refetch: vi.fn() }),
  usePatients: () => ({ data: [{ id: 'patient-1', full_name: 'Ana' }], isLoading: false, isError: false }),
  useStaff: () => ({ data: [{ id: 'staff-1', full_name: 'Dr. Rui' }], isLoading: false, isError: false }),
  useCreateAppointment: () => ({ mutate: createMutate, isPending: false }),
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

describe('AppointmentsPage creation workflow', () => {
  beforeEach(() => createMutate.mockReset())

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
})
