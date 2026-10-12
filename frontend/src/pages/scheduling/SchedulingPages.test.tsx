import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MyAgendaPage } from './MyAgendaPage'
import { SchedulingAdminPage } from './SchedulingAdminPage'

const h = vi.hoisted(() => ({
  mutate: vi.fn(),
  agenda: { appointments: [] as unknown[], absences: [] as unknown[], rules: [] as unknown[], staff_id: 'd1' },
  schedule: [] as unknown[],
}))

vi.mock('../../hooks/useScheduling', () => ({
  useSpecialties: () => ({ data: [{ id: 's1', name: 'Medicina Geral', active: true }], isError: false }),
  useAppointmentTypes: () => ({
    data: [{ id: 't1', name: 'Consulta de rotina', duration_minutes: 30, specialty_id: 's1', booking_mode: 'direct', active: true }],
    isError: false,
  }),
  useBookingSettings: () => ({
    data: { cancellation_deadline_hours: 24, waitlist_offer_minutes: 60, reminder_hours_before: 24, booking_horizon_days: 90, clinic_phone: null },
    isLoading: false,
    isError: false,
  }),
  useProfessionals: () => ({ data: [{ id: 'd1', full_name: 'Dra. Rita', staff_role: 'doctor', specialty_id: 's1', accepts_new_patients: true }], isError: false }),
  useSchedule: () => ({ data: h.schedule, isLoading: false, isError: false, dataUpdatedAt: 1 }),
  useAgenda: () => ({ data: h.agenda, isLoading: false, isError: false }),
  useSchedulingChange: () => ({ mutate: h.mutate, isPending: false }),
}))

type Callbacks = { onSuccess?: (value?: unknown) => void; onError?: (error: unknown) => void }
const last = () => h.mutate.mock.calls.at(-1) as [unknown, Callbacks]

beforeEach(() => {
  h.mutate.mockReset()
  h.schedule = []
  h.agenda = { appointments: [], absences: [], rules: [], staff_id: 'd1' }
})

describe('SchedulingAdminPage', () => {
  it('creates an appointment type with its specialty and booking mode', async () => {
    const user = userEvent.setup()
    render(<SchedulingAdminPage />)
    expect(screen.getByRole('heading', { level: 1, name: 'Agendas e marcações' })).toBeInTheDocument()
    const form = screen.getByRole('form', { name: 'Novo tipo de consulta' })
    await user.type(within(form).getByLabelText('Nome do tipo'), 'Primeira consulta')
    await user.clear(within(form).getByLabelText('Duração (minutos)'))
    await user.type(within(form).getByLabelText('Duração (minutos)'), '45')
    await user.selectOptions(within(form).getByLabelText('Especialidade'), 's1')
    await user.selectOptions(within(form).getByLabelText('Modo de marcação'), 'request')
    await user.click(within(form).getByRole('button', { name: 'Adicionar tipo de consulta' }))
    expect(last()[0]).toEqual({
      kind: 'createType',
      payload: { name: 'Primeira consulta', duration_minutes: 45, specialty_id: 's1', booking_mode: 'request' },
    })
  })

  it('edits the weekly schedule of a professional, with the types of their specialty', async () => {
    const user = userEvent.setup()
    render(<SchedulingAdminPage />)
    await user.selectOptions(screen.getByLabelText('Profissional'), 'd1')
    const form = screen.getByRole('form', { name: 'Agenda semanal' })
    await user.click(within(form).getByRole('button', { name: 'Adicionar bloco' }))
    await user.selectOptions(within(form).getByLabelText('Dia'), '2')
    expect(within(form).getByRole('checkbox', { name: 'Consulta de rotina' })).toBeChecked()
    await user.click(within(form).getByRole('button', { name: 'Guardar agenda semanal' }))
    expect(last()[0]).toEqual({
      kind: 'schedule',
      staffId: 'd1',
      rules: [{ weekday: 2, start_time: '09:00', end_time: '12:00', valid_from: null, valid_until: null, appointment_type_ids: ['t1'] }],
    })
    act(() => last()[1].onSuccess?.())
    expect(screen.getByText('Agenda semanal guardada.')).toBeInTheDocument()
  })

  it('saves the clinic rules (deadline, offer validity, reminder, horizon)', async () => {
    const user = userEvent.setup()
    render(<SchedulingAdminPage />)
    const deadline = screen.getByLabelText('Prazo para cancelar ou remarcar na app (horas antes)')
    await user.clear(deadline)
    await user.type(deadline, '48')
    await user.click(screen.getByRole('button', { name: 'Guardar regras' }))
    expect(last()[0]).toEqual({
      kind: 'settings',
      payload: { cancellation_deadline_hours: 48, waitlist_offer_minutes: 60, reminder_hours_before: 24, booking_horizon_days: 90 },
    })
  })
})

describe('MyAgendaPage', () => {
  it('blocks an absence in Lisbon time and warns about appointments inside it', async () => {
    const user = userEvent.setup()
    render(<MyAgendaPage />)
    expect(screen.getByRole('heading', { level: 1, name: 'A minha agenda' })).toBeInTheDocument()
    await user.type(screen.getByLabelText('Início'), '2027-04-02T09:00')
    await user.type(screen.getByLabelText('Fim'), '2027-04-02T13:00')
    await user.click(screen.getByRole('button', { name: 'Bloquear' }))
    expect(last()[0]).toEqual({
      kind: 'addAbsence',
      payload: { starts_at: '2027-04-02T08:00:00.000Z', ends_at: '2027-04-02T12:00:00.000Z', kind: 'vacation' },
    })
    act(() => last()[1].onSuccess?.({ conflicting_appointments: 2 }))
    expect(screen.getByRole('status')).toHaveTextContent('Há 2 consulta(s) marcada(s) nesse período')
  })

  it('refuses an end before the start without calling the API', async () => {
    const user = userEvent.setup()
    render(<MyAgendaPage />)
    await user.type(screen.getByLabelText('Início'), '2027-04-02T13:00')
    await user.type(screen.getByLabelText('Fim'), '2027-04-02T09:00')
    await user.click(screen.getByRole('button', { name: 'Bloquear' }))
    expect(h.mutate).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent('Indica o início e um fim posterior ao início.')
  })
})
