import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AppointmentRequestsPanel } from './AppointmentRequestsPanel'
import { MemoryRouter } from 'react-router-dom'

const session = vi.hoisted(() => ({ user: null as unknown }))
vi.mock('../hooks/useSession', () => ({ useSession: () => ({ user: session.user }) }))

type Call = { method: string; path: string; body: unknown }

function json(body: unknown, status = 200, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json', ...headers } })
}

const request: Record<string, unknown> = {
  id: 'r1',
  clinic_id: 'c1',
  patient_id: 'p1',
  patient_name: 'Ana Paciente',
  preferred_start: '2031-05-10T10:00:00Z',
  preferred_from: null,
  preferred_to: null,
  preferred_weekdays: null,
  preferred_period: null,
  appointment_type: null,
  specialty: null,
  staff_id: null,
  staff_name: null,
  reschedule_of_id: null,
  reschedule_of_start: null,
  proposed_staff_id: null,
  proposed_staff_name: null,
  proposed_start: null,
  proposed_duration_minutes: null,
  reason: 'Dor de cabeça',
  status: 'pending',
  appointment_id: null,
  decided_at: null,
  created_at: '2031-05-01T10:00:00Z',
}
const windowed = {
  ...request,
  id: 'r4',
  preferred_start: null,
  preferred_from: '2031-05-12',
  preferred_to: '2031-05-19',
  preferred_weekdays: [0, 2],
  preferred_period: 'morning',
  appointment_type: 'Fisioterapia',
  specialty: 'Reabilitação',
  staff_id: 's1',
  staff_name: 'Dr. Rui',
}

function setup(handler: (method: string, path: string, body: unknown) => Response | undefined, url = '/patient/consultas') {
  const calls: Call[] = []
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), 'http://localhost')
    const method = init?.method ?? 'GET'
    const body = init?.body ? JSON.parse(String(init.body)) : undefined
    calls.push({ method, path: url.pathname + url.search, body })
    const response = handler(method, url.pathname + url.search, body)
    if (!response) throw new Error(`unexpected ${method} ${url.pathname}${url.search}`)
    return response
  }))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[url]}><AppointmentRequestsPanel /></MemoryRouter></QueryClientProvider>)
  return calls
}

afterEach(() => vi.unstubAllGlobals())

describe('AppointmentRequestsPanel — patient', () => {
  it('shows nothing while the patient has no requests (booking is in "Marcar consulta")', async () => {
    session.user = { id: 'u1', role: 'patient', staff_role: null }
    const calls = setup(() => json([], 200, { 'X-Total-Count': '0' }))
    await waitFor(() => expect(calls).toHaveLength(1))
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Os meus pedidos' })).not.toBeInTheDocument())
  })

  it('shows the preferences and answers a proposal of the clinic', async () => {
    session.user = { id: 'u1', role: 'patient', staff_role: null }
    const proposal = { ...windowed, status: 'proposed', proposed_start: '2031-05-14T09:00:00Z', proposed_staff_name: 'Dr. Rui', proposed_duration_minutes: 30 }
    let listed: Array<Record<string, unknown>> = [proposal]
    const calls = setup((method, path) => {
      if (method === 'GET') return json(listed, 200, { 'X-Total-Count': String(listed.length) })
      if (path === '/api/v1/appointment-requests/r4/accept-proposal') {
        listed = [{ ...proposal, status: 'accepted', appointment_id: 'a9' }]
        return json(listed[0])
      }
      return undefined
    })
    const list = await screen.findByRole('list', { name: 'Pedidos em curso' })
    expect(within(list).getByText('Fisioterapia (Reabilitação)')).toBeInTheDocument()
    expect(within(list).getByText(/De 12\/05 a 19\/05 · segunda, quarta · manhã · Dr\. Rui/)).toBeInTheDocument()
    expect(within(list).getByText(/A clínica propõe:/)).toHaveTextContent('10:00')  // Lisbon summer time
    expect(within(list).getByText('Proposta da clínica')).toBeInTheDocument()
    await userEvent.click(within(list).getByRole('button', { name: 'Aceitar proposta' }))
    await screen.findByText('Pedidos anteriores (1)')
    expect(calls.some((c) => c.method === 'POST' && c.path === '/api/v1/appointment-requests/r4/accept-proposal')).toBe(true)
  })

  it('declines a proposal and shows the server refusal', async () => {
    session.user = { id: 'u1', role: 'patient', staff_role: null }
    const proposal = { ...windowed, status: 'proposed', proposed_start: '2031-05-14T09:00:00Z', proposed_staff_name: 'Dr. Rui', proposed_duration_minutes: 30 }
    setup((method, path) => {
      if (method === 'GET') return json([proposal], 200, { 'X-Total-Count': '1' })
      if (path.endsWith('/decline-proposal')) return json({ detail: 'O pedido já foi processado.' }, 409)
      return undefined
    })
    const list = await screen.findByRole('list', { name: 'Pedidos em curso' })
    await userEvent.click(within(list).getByRole('button', { name: 'Recusar proposta' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('O pedido já foi processado.')
  })

  it('cancels an open request; finished ones are listed apart without actions', async () => {
    session.user = { id: 'u1', role: 'patient', staff_role: null }
    let listed = [request, { ...request, id: 'r2', status: 'rejected' }, { ...request, id: 'r3', status: 'accepted', appointment_id: 'a1' }]
    const calls = setup((method, path) => {
      if (method === 'GET') return json(listed, 200, { 'X-Total-Count': String(listed.length) })
      if (path === '/api/v1/appointment-requests/r1/cancel') {
        listed = listed.map((r) => (r.id === 'r1' ? { ...r, status: 'cancelled' } : r))
        return json({ ...request, status: 'cancelled' })
      }
      return undefined
    })
    const open = await screen.findByRole('list', { name: 'Pedidos em curso' })
    const previous = screen.getByRole('list', { name: 'Pedidos anteriores', hidden: true })
    expect(within(previous).getByText('Recusado')).toBeInTheDocument()
    expect(within(previous).getByText('Aceite')).toBeInTheDocument()
    expect(within(previous).queryByRole('button', { hidden: true })).not.toBeInTheDocument()
    await userEvent.click(within(open).getByRole('button', { name: 'Cancelar pedido' }))
    await screen.findByText('Pedidos anteriores (3)')
    expect(calls.some((c) => c.path === '/api/v1/appointment-requests/r1/cancel')).toBe(true)
  })
})

describe('AppointmentRequestsPanel — staff', () => {
  const staffList = [
    { id: 's1', clinic_id: 'c1', full_name: 'Dr. Rui', staff_role: 'doctor', specialty: null, is_active: true },
    { id: 's2', clinic_id: 'c1', full_name: 'Receção', staff_role: 'admin', specialty: null, is_active: true },
  ]

  it('accepts a pending request with the chosen professional and slot', async () => {
    session.user = { id: 'u9', role: 'clinic_admin', staff_role: null }
    let listed: unknown[] = [{ ...request, reason: null }]
    const calls = setup((method, path) => {
      if (path.startsWith('/api/v1/staff')) return json(staffList)
      if (method === 'GET' && path.includes('status=proposed')) return json([], 200, { 'X-Total-Count': '0' })
      if (method === 'GET') return json(listed, 200, { 'X-Total-Count': String(listed.length) })
      if (path === '/api/v1/appointment-requests/r1/accept') {
        listed = []
        return json({ ...request, status: 'accepted', appointment_id: 'a1' })
      }
      return undefined
    })
    const list = await screen.findByRole('list', { name: 'Pedidos de consulta pendentes' })
    expect(within(list).getByText('Ana Paciente')).toBeInTheDocument()
    expect(within(list).queryByText(/Motivo/)).not.toBeInTheDocument()
    await userEvent.click(within(list).getByRole('button', { name: 'Aceitar…' }))
    const form = screen.getByRole('form', { name: 'Marcar consulta para Ana Paciente' })
    const select = within(form).getByLabelText('Profissional')
    expect(within(select).getAllByRole('option').map((o) => o.textContent)).toEqual(['Escolha', 'Dr. Rui'])
    await userEvent.selectOptions(select, 's1')
    await userEvent.click(within(form).getByRole('button', { name: 'Marcar consulta' }))
    expect(await screen.findByText('Não há pedidos pendentes.')).toBeInTheDocument()
    const sent = calls.find((c) => c.path.endsWith('/accept'))?.body as Record<string, unknown>
    // The patient's time, read and sent as Lisbon wall clock; the duration is left to the server (type's).
    expect(sent).toEqual({ staff_id: 's1', scheduled_at: '2031-05-10T10:00:00.000Z' })
    expect(calls.some((c) => c.method === 'GET' && c.path.includes('status=pending'))).toBe(true)
  })

  it('shows a conflict when the request was already processed, and rejects', async () => {
    session.user = { id: 'u8', role: 'staff', staff_role: 'doctor' }
    let listed: unknown[] = [request]
    setup((method, path) => {
      if (path.startsWith('/api/v1/staff')) return json(staffList)
      if (method === 'GET' && path.includes('status=proposed')) return json([], 200, { 'X-Total-Count': '0' })
      if (method === 'GET') return json(listed, 200, { 'X-Total-Count': String(listed.length) })
      if (path.endsWith('/accept')) return json({ detail: 'O pedido já foi processado.' }, 409)
      if (path.endsWith('/reject')) {
        listed = []
        return json({ ...request, status: 'rejected' })
      }
      return undefined
    })
    const list = await screen.findByRole('list', { name: 'Pedidos de consulta pendentes' })
    expect(within(list).getByText('Motivo: Dor de cabeça')).toBeInTheDocument()
    await userEvent.click(within(list).getByRole('button', { name: 'Aceitar…' }))
    await userEvent.selectOptions(screen.getByLabelText('Profissional'), 's1')
    await userEvent.click(screen.getByRole('button', { name: 'Marcar consulta' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('O pedido já foi processado.')
    await userEvent.click(within(list).getByRole('button', { name: 'Recusar pedido de Ana Paciente' }))
    expect(await screen.findByText('Não há pedidos pendentes.')).toBeInTheDocument()
  })

  it('proposes a time to the patient, prefilled with their preferred professional, and lists it apart', async () => {
    session.user = { id: 'u9', role: 'clinic_admin', staff_role: null }
    let pending: unknown[] = [windowed]
    let proposed: unknown[] = []
    const calls = setup((method, path) => {
      if (path.startsWith('/api/v1/staff')) return json(staffList)
      if (method === 'GET' && path.includes('status=proposed')) return json(proposed, 200, { 'X-Total-Count': String(proposed.length) })
      if (method === 'GET') return json(pending, 200, { 'X-Total-Count': String(pending.length) })
      if (path === '/api/v1/appointment-requests/r4/propose') {
        const done = { ...windowed, status: 'proposed', proposed_start: '2031-05-14T09:00:00Z', proposed_staff_id: 's1', proposed_staff_name: 'Dr. Rui', proposed_duration_minutes: 45 }
        pending = []
        proposed = [done]
        return json(done)
      }
      return undefined
    })
    const list = await screen.findByRole('list', { name: 'Pedidos de consulta pendentes' })
    expect(within(list).getByText('Fisioterapia (Reabilitação)')).toBeInTheDocument()
    await userEvent.click(within(list).getByRole('button', { name: 'Propor horário…' }))
    const form = screen.getByRole('form', { name: 'Propor horário a Ana Paciente' })
    expect(within(form).getByLabelText('Profissional')).toHaveValue('s1')
    await userEvent.type(within(form).getByLabelText('Data e hora'), '2031-05-14T10:00')
    await userEvent.type(within(form).getByLabelText('Duração (min)'), '45')
    await userEvent.click(within(form).getByRole('button', { name: 'Enviar proposta' }))
    const waiting = await screen.findByRole('list', { name: 'Propostas à espera do paciente' })
    expect(within(waiting).getByText(/Proposto:/)).toHaveTextContent('10:00')
    const sent = calls.find((c) => c.path.endsWith('/propose'))?.body
    expect(sent).toEqual({ staff_id: 's1', scheduled_at: '2031-05-14T09:00:00.000Z', duration_minutes: 45 })
    expect(within(waiting).getByRole('button', { name: 'Retirar proposta a Ana Paciente' })).toBeInTheDocument()
  })
})
