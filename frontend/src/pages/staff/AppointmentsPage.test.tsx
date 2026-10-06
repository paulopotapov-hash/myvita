import { act, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../lib/apiClient'
import { AppointmentsPage } from './AppointmentsPage'

const { appointmentState, cancelMutate, createMutate, pending, sessionState, updateMutate } = vi.hoisted(() => ({
  appointmentState: { rows: [] as Array<Record<string, unknown>> },
  cancelMutate: vi.fn(),
  createMutate: vi.fn(),
  pending: { create: false, update: false, cancel: false },
  sessionState: { role: 'staff', staff_role: 'doctor' as string | null },
  updateMutate: vi.fn(),
}))

vi.mock('../../hooks/useSession', () => ({
  useSession: () => ({
    user: { id: 'doctor-1', email: 'doctor@example.pt', full_name: 'Doctor', clinic_id: 'clinic-1', patient_id: null, ...sessionState },
  }),
}))

vi.mock('../../hooks/useClinicData', () => ({
  useAppointments: () => ({ data: appointmentState.rows, isLoading: false, isError: false, refetch: vi.fn() }),
  usePatients: () => ({ data: [{ id: 'patient-1', full_name: 'Ana' }], isLoading: false, isError: false }),
  useStaff: () => ({ data: [{ id: 'staff-1', full_name: 'Dr. Rui' }], isLoading: false, isError: false }),
  useCreateAppointment: () => ({ mutate: createMutate, isPending: pending.create }),
  useUpdateAppointment: () => ({ mutate: updateMutate, isPending: pending.update }),
  useCancelAppointment: () => ({ mutate: cancelMutate, isPending: pending.cancel }),
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
    pending.create = pending.update = pending.cancel = false
    sessionState.role = 'staff'
    sessionState.staff_role = 'doctor'
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

  describe('validation, feedback and pending states', () => {
    const appointment = {
      id: 'appointment-1', clinic_id: 'clinic-1', patient_id: 'patient-1', staff_id: 'staff-1',
      scheduled_at: '2026-10-20T10:30:00Z', duration_minutes: 30, status: 'scheduled', reason: 'Consulta anual',
    }

    async function openDialog() {
      appointmentState.rows = [appointment]
      const user = userEvent.setup()
      renderPage()
      await user.click(screen.getByRole('button', { name: 'Detalhes' }))
      return { user, dialog: screen.getByRole('dialog') }
    }

    it('shows required-field errors next to each field and sends nothing', async () => {
      const user = userEvent.setup()
      renderPage()
      await user.click(screen.getByRole('button', { name: 'Marcar consulta' }))
      expect(screen.getByText('Escolhe um paciente.')).toBeInTheDocument()
      expect(screen.getByText('Escolhe um profissional.')).toBeInTheDocument()
      expect(screen.getByText('Escolhe data e hora.')).toBeInTheDocument()
      expect(screen.getByLabelText('Paciente')).toHaveAttribute('aria-invalid', 'true')
      expect(createMutate).not.toHaveBeenCalled()
    })

    it('rejects an out-of-range duration locally with the shared message', async () => {
      const user = userEvent.setup()
      renderPage()
      await user.selectOptions(screen.getByLabelText('Paciente'), 'patient-1')
      await user.selectOptions(screen.getByLabelText('Profissional'), 'staff-1')
      fireEvent.change(screen.getByLabelText('Data e hora'), { target: { value: '2026-10-20T10:30' } })
      await user.clear(screen.getByLabelText('Duração (minutos)'))
      await user.type(screen.getByLabelText('Duração (minutos)'), '3')
      await user.click(screen.getByRole('button', { name: 'Marcar consulta' }))
      expect(screen.getByText('A duração mínima é de 5 minutos.')).toBeInTheDocument()
      expect(createMutate).not.toHaveBeenCalled()
    })

    it('never sends a reason for roles that cannot record one (the backend answers 403)', async () => {
      sessionState.role = 'clinic_admin'
      sessionState.staff_role = null
      const user = userEvent.setup()
      renderPage()
      expect(screen.queryByLabelText('Motivo (opcional)')).not.toBeInTheDocument()
      await user.selectOptions(screen.getByLabelText('Paciente'), 'patient-1')
      await user.selectOptions(screen.getByLabelText('Profissional'), 'staff-1')
      fireEvent.change(screen.getByLabelText('Data e hora'), { target: { value: '2026-10-20T10:30' } })
      await user.click(screen.getByRole('button', { name: 'Marcar consulta' }))
      const payload = createMutate.mock.calls.at(-1)?.[0] as Record<string, unknown>
      expect(payload).toBeDefined()
      expect(payload).not.toHaveProperty('reason')
    })

    it('confirms creation, and shows backend field errors next to the field', async () => {
      await fillAndSubmit()
      const options = createMutate.mock.calls.at(-1)?.[1] as {
        onSuccess: () => void
        onError: (error: unknown) => void
      }
      act(() => options.onError(new ApiError(422, 'x', { fieldErrors: { scheduled_at: 'Data inválida' } })))
      expect(await screen.findByText('Data inválida')).toBeInTheDocument()
      expect(screen.getByLabelText('Data e hora')).toHaveAttribute('aria-invalid', 'true')
      act(() => options.onSuccess())
      expect(await screen.findByRole('status')).toHaveTextContent('Consulta marcada com sucesso.')
    })

    it('disables the create button while the request is pending', () => {
      pending.create = true
      renderPage()
      const button = screen.getByRole('button', { name: 'Marcar consulta' })
      expect(button).toBeDisabled()
      expect(button).toHaveAttribute('aria-busy', 'true')
    })

    it('validates the duration in the detail dialog before calling the API', async () => {
      const { user, dialog } = await openDialog()
      const duration = within(dialog).getByLabelText('Duração (minutos)')
      await user.clear(duration)
      await user.type(duration, '500')
      await user.click(screen.getByRole('button', { name: 'Guardar alterações' }))
      expect(screen.getByText('A duração máxima é de 480 minutos.')).toBeInTheDocument()
      expect(updateMutate).not.toHaveBeenCalled()
    })

    it('closes the dialog and confirms an update on the page', async () => {
      const { user } = await openDialog()
      await user.click(screen.getByRole('button', { name: 'Guardar alterações' }))
      const options = updateMutate.mock.calls.at(-1)?.[1] as { onSuccess: () => void }
      act(() => options.onSuccess())
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
      expect(await screen.findByRole('status')).toHaveTextContent('Consulta atualizada.')
    })

    it('confirms a cancellation on the page and shows a failed one inside the dialog', async () => {
      const { user } = await openDialog()
      await user.click(screen.getByRole('button', { name: 'Cancelar consulta' }))
      const options = cancelMutate.mock.calls.at(-1)?.[1] as {
        onSuccess: () => void
        onError: (error: unknown) => void
      }
      act(() => options.onError(new ApiError(409, 'x', { detail: 'Consulta já cancelada.' })))
      expect(await screen.findByRole('alert')).toHaveTextContent('Consulta já cancelada.')
      expect(screen.getByRole('dialog')).toBeInTheDocument()
      act(() => options.onSuccess())
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
      expect(await screen.findByRole('status')).toHaveTextContent('Consulta cancelada.')
    })

    it('does not cancel when the confirmation is declined and locks both actions while saving', async () => {
      vi.spyOn(window, 'confirm').mockReturnValue(false)
      const { user } = await openDialog()
      await user.click(screen.getByRole('button', { name: 'Cancelar consulta' }))
      expect(cancelMutate).not.toHaveBeenCalled()
    })

    it('disables save and cancel together while either request is pending', async () => {
      pending.update = true
      await openDialog()
      expect(screen.getByRole('button', { name: 'Guardar alterações' })).toBeDisabled()
      expect(screen.getByRole('button', { name: 'Cancelar consulta' })).toBeDisabled()
    })
  })

  describe('dialog accessibility', () => {
    it('moves focus into the dialog, closes on Escape and returns focus to the opener', async () => {
      appointmentState.rows = [{
        id: 'appointment-1', clinic_id: 'clinic-1', patient_id: 'patient-1', staff_id: 'staff-1',
        scheduled_at: '2026-10-20T10:30:00Z', duration_minutes: 30, status: 'scheduled', reason: 'Consulta anual',
      }]
      const user = userEvent.setup()
      renderPage()
      const opener = screen.getByRole('button', { name: 'Detalhes' })
      await user.click(opener)
      expect(screen.getByRole('dialog', { name: 'Detalhe da consulta' })).toHaveFocus()
      await user.keyboard('{Escape}')
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
      expect(opener).toHaveFocus()
    })

    it('focuses the first invalid field of the create form', async () => {
      const user = userEvent.setup()
      renderPage()
      await user.click(screen.getByRole('button', { name: 'Marcar consulta' }))
      expect(screen.getByLabelText('Paciente')).toHaveFocus()
    })
  })
})
