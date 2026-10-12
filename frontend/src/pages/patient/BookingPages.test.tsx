import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../lib/apiClient'
import { BookingFlowPage } from './BookingFlowPage'
import { PatientAppointmentDetailPage } from './PatientAppointmentDetailPage'
import { PatientAppointmentsPage } from './PatientAppointmentsPage'
import { RescheduleFlowPage } from './RescheduleFlowPage'

const DAY = 86_400_000
const h = vi.hoisted(() => ({
  appointments: [] as unknown[],
  book: vi.fn(),
  refetchSlots: vi.fn(),
  slots: [] as unknown[],
  professionals: [] as unknown[],
  slotArgs: [] as unknown[][],
  rescheduleSlotArgs: [] as unknown[][],
  cancel: vi.fn(),
  reschedule: vi.fn(),
  ask: vi.fn(),
  waitlist: [] as unknown[],
  waitlistChange: vi.fn(),
  acceptOffer: vi.fn(),
}))

vi.mock('../../hooks/useWaitlist', () => ({
  useWaitlist: () => ({ data: h.waitlist, isSuccess: true }),
  useWaitlistChange: () => ({ mutate: h.waitlistChange, isPending: false }),
  useAcceptOffer: () => ({ mutate: h.acceptOffer, isPending: false, variables: undefined }),
}))

vi.mock('../../services/appointmentRequests', () => ({
  appointmentRequestsService: { create: (payload: unknown) => h.ask(payload) },
}))

vi.mock('../../components/AppointmentRequestsPanel', () => ({
  AppointmentRequestsPanel: () => <section aria-label="Pedidos de consulta">Pedidos</section>,
}))
vi.mock('../../hooks/useClinicData', () => ({
  useAppointments: () => ({ data: h.appointments, isLoading: false, isError: false }),
  useAppointment: (id: string) => ({ data: h.appointments.find((item) => (item as { id: string }).id === id), isLoading: false, isError: false }),
}))
vi.mock('../../hooks/useScheduling', () => ({
  useAppointmentTypes: () => ({
    data: [
      { id: 't-gp', name: 'Consulta de rotina', duration_minutes: 30, specialty_id: 's-gp', booking_mode: 'direct', active: true },
      { id: 't-ped', name: 'Consulta de rotina', duration_minutes: 30, specialty_id: 's-ped', booking_mode: 'direct', active: true },
      { id: 't-req', name: 'Primeira consulta', duration_minutes: 45, specialty_id: 's-gp', booking_mode: 'request', active: true },
    ],
    isLoading: false,
    isError: false,
  }),
  useSpecialties: () => ({ data: [{ id: 's-gp', name: 'Medicina Geral', active: true }, { id: 's-ped', name: 'Pediatria', active: true }] }),
  useBookingSettings: () => ({ data: { booking_horizon_days: 90, cancellation_deadline_hours: 24, clinic_address: 'Rua Sintética, 1', clinic_phone: '210000000' } }),
  useBookableProfessionals: (typeId: string) => ({ data: typeId ? h.professionals : undefined, isLoading: false, isError: false }),
  useSlots: (...args: unknown[]) => {
    h.slotArgs.push(args)
    return { data: args[0] ? h.slots : undefined, isLoading: false, isError: false, refetch: h.refetchSlots }
  },
  useBook: () => ({ mutate: h.book, isPending: false }),
  useCancelBooking: () => ({ mutate: h.cancel, isPending: false }),
  useReschedule: () => ({ mutate: h.reschedule, isPending: false }),
  useRescheduleSlots: (...args: unknown[]) => {
    h.rescheduleSlotArgs.push(args)
    return { data: args[4] ? h.slots : undefined, isLoading: false, isError: false, refetch: h.refetchSlots }
  },
}))

function iso(days: number, hour: number) {
  const date = new Date(Date.now() + days * DAY)
  date.setUTCHours(hour, 0, 0, 0)
  return date.toISOString()
}
function appointment(id: string, days: number, status: string, type = 'Consulta de rotina', extra: Record<string, unknown> = {}) {
  return {
    view: 'patient', id, staff_name: 'Dra. Rita', scheduled_at: iso(days, 10), ends_at: iso(days, 11), duration_minutes: 30, status,
    reason: null, appointment_type: type, specialty: 'Medicina Geral', location: 'Rua Sintética, 1',
    can_change: status === 'confirmed' || status === 'scheduled', change_until: iso(days - 1, 10), booking_mode: 'direct', ...extra,
  }
}

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{location.pathname}</output>
}

function renderAt(path: string) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/patient/consultas" element={<PatientAppointmentsPage />} />
          <Route path="/patient/consultas/marcar" element={<BookingFlowPage />} />
          <Route path="/patient/consultas/:appointmentId" element={<PatientAppointmentDetailPage />} />
          <Route path="/patient/consultas/:appointmentId/remarcar" element={<RescheduleFlowPage />} />
        </Routes>
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  h.appointments = []
  h.book.mockReset()
  h.refetchSlots.mockReset()
  h.slotArgs = []
  h.rescheduleSlotArgs = []
  h.cancel.mockReset()
  h.reschedule.mockReset()
  h.ask.mockReset()
  h.ask.mockResolvedValue({ id: 'req-1' })
  h.waitlist = []
  h.waitlistChange.mockReset()
  h.acceptOffer.mockReset()
  h.professionals = [
    { id: 'd-known', full_name: 'Dra. Rita', known: true },
    { id: 'd-new', full_name: 'Dr. Rui', known: false },
  ]
  h.slots = [
    { starts_at: iso(3, 9), ends_at: iso(3, 9).replace('T09', 'T09'), staff_id: 'd-known', staff_name: 'Dra. Rita' },
    { starts_at: iso(3, 10), ends_at: iso(3, 10), staff_id: 'd-new', staff_name: 'Dr. Rui' },
  ]
})

describe('As minhas consultas', () => {
  it('splits upcoming and past, hides cancelled ones by default and offers booking prominently', async () => {
    h.appointments = [appointment('up', 5, 'confirmed'), appointment('old', -5, 'completed'), appointment('gone', 6, 'cancelled')]
    const user = userEvent.setup()
    renderAt('/patient/consultas')
    expect(screen.getByRole('link', { name: 'Marcar consulta' })).toHaveAttribute('href', '/patient/consultas/marcar')
    const panel = screen.getByRole('tabpanel')
    expect(within(panel).getAllByRole('link')).toHaveLength(1)
    expect(within(panel).getByRole('link')).toHaveAttribute('href', '/patient/consultas/up')
    await user.click(screen.getByRole('checkbox', { name: /Mostrar consultas canceladas \(1\)/ }))
    expect(within(screen.getByRole('tabpanel')).getAllByRole('link')).toHaveLength(2)
    await user.click(screen.getByRole('tab', { name: 'Passadas' }))
    expect(within(screen.getByRole('tabpanel')).getByRole('link')).toHaveAttribute('href', '/patient/consultas/old')
    expect(screen.getByRole('region', { name: 'Pedidos de consulta' })).toBeInTheDocument()
  })

  it('opens old "?consulta=" links on the appointment page', () => {
    h.appointments = [appointment('up', 5, 'confirmed')]
    renderAt('/patient/consultas?consulta=up')
    expect(screen.getByTestId('location')).toHaveTextContent('/patient/consultas/up')
    expect(screen.getByRole('region', { name: 'Detalhes da consulta' })).toHaveTextContent('Rua Sintética, 1')
  })
})

describe('Marcar consulta', () => {
  it('goes through the five steps and books "Qualquer disponível"', async () => {
    const user = userEvent.setup()
    renderAt('/patient/consultas/marcar')
    expect(screen.getByText('Passo 1 de 5')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Consulta de rotina/ }))
    expect(screen.getByRole('heading', { level: 2, name: 'Especialidade' })).toHaveFocus()
    await user.click(screen.getByRole('button', { name: /Pediatria/ }))
    // Known professionals first, and the "any" option.
    const options = within(screen.getByRole('region', { name: 'Profissional' })).getAllByRole('listitem').map((item) => item.textContent)
    expect(options).toEqual(['Qualquer disponívelMostra os horários de todos os profissionais', 'Dra. RitaJá tiveste consulta', 'Dr. Rui'])
    await user.click(screen.getByRole('button', { name: /Qualquer disponível/ }))
    expect(h.slotArgs.at(-1)?.[0]).toBe('t-ped')
    expect(h.slotArgs.at(-1)?.[3]).toBeUndefined()
    await user.click(screen.getAllByRole('button', { name: /Dr\. Rui/ })[0])
    expect(screen.getByText('Passo 5 de 5')).toBeInTheDocument()
    expect(screen.getByText('Rua Sintética, 1')).toBeInTheDocument()
    expect(screen.getByText(/até 24 horas antes/)).toBeInTheDocument()
    await user.type(screen.getByLabelText('Motivo da consulta (opcional)'), 'Febre')
    await user.click(screen.getByRole('button', { name: 'Confirmar marcação' }))
    expect(h.book).toHaveBeenCalledWith({ appointment_type_id: 't-ped', starts_at: h.slots[1] && (h.slots[1] as { starts_at: string }).starts_at, reason: 'Febre' }, expect.any(Object))
    // Never shown as booked before the server answers; then the appointment page.
    expect(screen.getByTestId('location')).toHaveTextContent('/patient/consultas/marcar')
    const [, callbacks] = h.book.mock.calls[0] as [unknown, { onSuccess: (value: { id: string }) => void }]
    act(() => callbacks.onSuccess({ id: 'new-id' }))
    expect(screen.getByTestId('location')).toHaveTextContent('/patient/consultas/new-id')
  })

  it('goes back to the refreshed slots when the slot was taken meanwhile', async () => {
    const user = userEvent.setup()
    renderAt('/patient/consultas/marcar')
    await user.click(screen.getByRole('button', { name: /Consulta de rotina/ }))
    await user.click(screen.getByRole('button', { name: /Medicina Geral/ }))
    await user.click(screen.getByRole('button', { name: /Dra\. Rita/ }))
    expect(h.slotArgs.at(-1)?.[3]).toBe('d-known')
    await user.click(screen.getAllByRole('button', { name: /,/ })[0])
    await user.click(screen.getByRole('button', { name: 'Confirmar marcação' }))
    const [, callbacks] = h.book.mock.calls[0] as [unknown, { onError: (error: unknown) => void }]
    act(() => callbacks.onError(new ApiError(409, 'x', { detail: 'Este horário já não está disponível. Escolhe outro.' })))
    expect(screen.getByText('Passo 4 de 5')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('Este horário já não está disponível. Escolhe outro.')
    expect(h.refetchSlots).toHaveBeenCalled()
  })

  it('turns "só por pedido" types into a request with preferences (step 4) and a summary', async () => {
    const user = userEvent.setup()
    renderAt('/patient/consultas/marcar')
    await user.click(screen.getByRole('button', { name: /Primeira consulta/ }))
    await user.click(screen.getByRole('button', { name: /Medicina Geral/ }))
    expect(screen.getByRole('heading', { level: 2, name: 'Profissional' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Dr\. Rui/ }))
    expect(screen.getByRole('heading', { level: 2, name: 'Preferências' })).toBeInTheDocument()
    expect(h.slotArgs.every((args) => !args[0])).toBe(true)
    const form = screen.getByRole('form', { name: 'Preferências para a consulta' })
    await user.click(within(form).getByRole('checkbox', { name: 'Terça' }))
    await user.click(within(form).getByRole('radio', { name: 'Tarde' }))
    await user.type(within(form).getByLabelText('Motivo da consulta (opcional)'), 'Primeira vez')
    await user.click(within(form).getByRole('button', { name: 'Continuar' }))
    expect(screen.getByText('Passo 5 de 5')).toBeInTheDocument()
    expect(screen.getByText(/terça · tarde/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Enviar pedido' }))
    expect(h.ask).toHaveBeenCalledWith(expect.objectContaining({
      appointment_type_id: 't-req', staff_id: 'd-new', preferred_weekdays: [1], preferred_period: 'afternoon', reason: 'Primeira vez',
      preferred_from: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
    }))
    await screen.findByText('/patient/consultas')
  })
})

describe('Detalhe da consulta', () => {
  it('offers cancel and reschedule until the deadline and cancels after confirmation', async () => {
    h.appointments = [appointment('up', 5, 'confirmed')]
    const user = userEvent.setup()
    renderAt('/patient/consultas/up')
    const actions = screen.getByRole('region', { name: 'Alterar a consulta' })
    expect(actions).toHaveTextContent('Podes cancelar ou remarcar na app até')
    expect(within(actions).getByRole('link', { name: 'Remarcar' })).toHaveAttribute('href', '/patient/consultas/up/remarcar')
    await user.click(within(actions).getByRole('button', { name: 'Cancelar consulta' }))
    const dialog = screen.getByRole('alertdialog', { name: 'Cancelar a consulta?' })
    await user.click(within(dialog).getByRole('button', { name: 'Cancelar consulta' }))
    expect(h.cancel).toHaveBeenCalledWith('up', expect.any(Object))
    const [, callbacks] = h.cancel.mock.calls[0] as [unknown, { onSuccess: () => void }]
    act(() => callbacks.onSuccess())
    expect(screen.getByText('Consulta cancelada. O horário ficou livre.')).toBeInTheDocument()
  })

  it('after the deadline shows the clinic phone instead of the actions', () => {
    h.appointments = [appointment('soon', 0, 'confirmed', 'Consulta de rotina', { can_change: false })]
    renderAt('/patient/consultas/soon')
    const notice = screen.getByRole('region', { name: 'Alterar a consulta' })
    expect(notice).toHaveTextContent('Já não é possível cancelar ou remarcar esta consulta na app.')
    expect(within(notice).getByRole('link', { name: '210000000' })).toHaveAttribute('href', 'tel:210000000')
    expect(screen.queryByRole('button', { name: 'Cancelar consulta' })).not.toBeInTheDocument()
  })

  it('offers nothing to change on a cancelled appointment', () => {
    h.appointments = [appointment('gone', 5, 'cancelled')]
    renderAt('/patient/consultas/gone')
    expect(screen.queryByRole('region', { name: 'Alterar a consulta' })).not.toBeInTheDocument()
  })
})

describe('Remarcar', () => {
  it('moves a direct appointment to a free slot and opens the new one', async () => {
    h.appointments = [appointment('up', 5, 'confirmed')]
    const user = userEvent.setup()
    renderAt('/patient/consultas/up/remarcar')
    await user.click(screen.getByRole('button', { name: /Com Dra\. Rita/ }))
    expect(h.rescheduleSlotArgs.at(-1)?.slice(0, 1)).toEqual(['up'])
    expect(h.rescheduleSlotArgs.at(-1)?.[3]).toBe('same')
    await user.click(screen.getAllByRole('button', { name: /,/ })[0])
    expect(screen.getByText('A consulta atual é cancelada ao confirmar.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Confirmar remarcação' }))
    expect(h.reschedule).toHaveBeenCalledWith({ appointmentId: 'up', starts_at: (h.slots[0] as { starts_at: string }).starts_at }, expect.any(Object))
    const [, callbacks] = h.reschedule.mock.calls[0] as [unknown, { onSuccess: (value: { id: string }) => void }]
    act(() => callbacks.onSuccess({ id: 'moved' }))
    expect(screen.getByTestId('location')).toHaveTextContent('/patient/consultas/moved')
  })

  it('returns to fresh slots when the new slot was taken meanwhile', async () => {
    h.appointments = [appointment('up', 5, 'confirmed')]
    const user = userEvent.setup()
    renderAt('/patient/consultas/up/remarcar')
    await user.click(screen.getByRole('button', { name: /Qualquer disponível/ }))
    await user.click(screen.getAllByRole('button', { name: /Dr\. Rui/ })[0])
    await user.click(screen.getByRole('button', { name: 'Confirmar remarcação' }))
    expect(h.reschedule).toHaveBeenCalledWith(expect.objectContaining({ staff_id: 'd-new' }), expect.any(Object))
    const [, callbacks] = h.reschedule.mock.calls[0] as [unknown, { onError: (error: unknown) => void }]
    act(() => callbacks.onError(new ApiError(409, 'x', { detail: 'Este horário já não está disponível. Escolhe outro.' })))
    expect(screen.getByRole('heading', { level: 2, name: 'Horário' })).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('Este horário já não está disponível.')
    expect(h.refetchSlots).toHaveBeenCalled()
  })

  it('asks the clinic to move a "só por pedido" appointment', async () => {
    h.appointments = [appointment('req', 5, 'confirmed', 'Primeira consulta', { booking_mode: 'request' })]
    const user = userEvent.setup()
    renderAt('/patient/consultas/req/remarcar')
    const form = screen.getByRole('form', { name: 'Preferências para a consulta' })
    expect(within(form).queryByLabelText('Motivo da consulta (opcional)')).not.toBeInTheDocument()
    await user.click(within(form).getByRole('radio', { name: 'Manhã' }))
    await user.click(within(form).getByRole('button', { name: 'Enviar pedido de remarcação' }))
    expect(h.ask).toHaveBeenCalledWith(expect.objectContaining({ reschedule_of_id: 'req', preferred_period: 'morning' }))
    await screen.findByText('/patient/consultas/req')
  })
})

describe('Lista de espera', () => {
  it('joins with the chosen scope from the appointment page, and shows how to leave', async () => {
    h.appointments = [appointment('up', 9, 'confirmed')]
    const user = userEvent.setup()
    const view = renderAt('/patient/consultas/up')
    const section = screen.getByRole('region', { name: 'Lista de espera' })
    await user.click(within(section).getByRole('radio', { name: 'Qualquer profissional da especialidade' }))
    await user.click(within(section).getByRole('button', { name: 'Entrar na lista de espera' }))
    expect(h.waitlistChange).toHaveBeenCalledWith({ kind: 'join', appointmentId: 'up', scope: 'specialty' }, expect.any(Object))

    h.waitlist = [{ id: 'e1', appointment_id: 'up', scope: 'professional', status: 'active', created_at: iso(0, 9), offers: [] }]
    view.unmount()
    renderAt('/patient/consultas/up')
    const listed = screen.getByRole('region', { name: 'Lista de espera' })
    expect(listed).toHaveTextContent('Estás na lista de espera (com Dra. Rita)')
    await user.click(within(listed).getByRole('button', { name: 'Sair da lista de espera' }))
    expect(h.waitlistChange).toHaveBeenLastCalledWith({ kind: 'leave', entryId: 'e1' }, expect.any(Object))
  })

  it('is not offered for "só por pedido" appointments', () => {
    h.appointments = [appointment('req', 9, 'confirmed', 'Primeira consulta', { booking_mode: 'request' })]
    renderAt('/patient/consultas/req')
    expect(screen.queryByRole('region', { name: 'Lista de espera' })).not.toBeInTheDocument()
  })

  it('offers earlier slots on "As minhas consultas" and opens the new appointment once accepted', async () => {
    h.appointments = [appointment('up', 9, 'confirmed')]
    h.waitlist = [{
      id: 'e1', appointment_id: 'up', scope: 'professional', status: 'active', created_at: iso(0, 9),
      offers: [{ id: 'o1', starts_at: iso(2, 9), ends_at: iso(2, 10), staff_name: 'Dra. Rita', expires_at: iso(0, 23) }],
    }]
    const user = userEvent.setup()
    renderAt('/patient/consultas')
    const offers = screen.getByRole('list', { name: 'Vagas oferecidas' })
    expect(offers).toHaveTextContent('Dra. Rita')
    await user.click(within(offers).getByRole('button', { name: 'Aceitar vaga' }))
    const [offerId, callbacks] = h.acceptOffer.mock.calls[0] as [string, { onSuccess: (value: { id: string }) => void }]
    expect(offerId).toBe('o1')
    h.appointments = [...h.appointments, appointment('earlier', 2, 'confirmed')]
    act(() => callbacks.onSuccess({ id: 'earlier' }))
    expect(screen.getByTestId('location')).toHaveTextContent('/patient/consultas/earlier')
    expect(screen.getByText('Consulta antecipada. A anterior foi cancelada.')).toBeInTheDocument()
  })
})
