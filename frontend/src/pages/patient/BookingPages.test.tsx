import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../lib/apiClient'
import { BookingFlowPage } from './BookingFlowPage'
import { PatientAppointmentDetailPage } from './PatientAppointmentDetailPage'
import { PatientAppointmentsPage } from './PatientAppointmentsPage'

const DAY = 86_400_000
const h = vi.hoisted(() => ({
  appointments: [] as unknown[],
  book: vi.fn(),
  refetchSlots: vi.fn(),
  slots: [] as unknown[],
  professionals: [] as unknown[],
  slotArgs: [] as unknown[][],
}))

vi.mock('../../components/AppointmentRequestsPanel', () => ({
  AppointmentRequestsPanel: () => <section aria-label="Pedidos de consulta">Pedidos</section>,
  REQUEST_FORM_ANCHOR: 'pedir-consulta',
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
}))

function iso(days: number, hour: number) {
  const date = new Date(Date.now() + days * DAY)
  date.setUTCHours(hour, 0, 0, 0)
  return date.toISOString()
}
function appointment(id: string, days: number, status: string, type = 'Consulta de rotina') {
  return {
    view: 'patient', id, staff_name: 'Dra. Rita', scheduled_at: iso(days, 10), ends_at: iso(days, 11), duration_minutes: 30, status,
    reason: null, appointment_type: type, specialty: 'Medicina Geral', location: 'Rua Sintética, 1',
  }
}

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{location.pathname}</output>
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/patient/consultas" element={<PatientAppointmentsPage />} />
        <Route path="/patient/consultas/marcar" element={<BookingFlowPage />} />
        <Route path="/patient/consultas/:appointmentId" element={<PatientAppointmentDetailPage />} />
      </Routes>
      <LocationProbe />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  h.appointments = []
  h.book.mockReset()
  h.refetchSlots.mockReset()
  h.slotArgs = []
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

  it('sends "só por pedido" types to the request form instead of slots', async () => {
    const user = userEvent.setup()
    renderAt('/patient/consultas/marcar')
    await user.click(screen.getByRole('button', { name: /Primeira consulta/ }))
    await user.click(screen.getByRole('button', { name: /Medicina Geral/ }))
    expect(screen.getByRole('link', { name: 'Fazer um pedido de consulta' })).toHaveAttribute('href', '/patient/consultas#pedir-consulta')
    expect(h.slotArgs.every((args) => !args[0])).toBe(true)
  })
})
