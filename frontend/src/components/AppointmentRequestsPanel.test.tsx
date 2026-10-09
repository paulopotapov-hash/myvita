import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AppointmentRequestsPanel } from './AppointmentRequestsPanel'

const session = vi.hoisted(() => ({ user: null as unknown }))
vi.mock('../hooks/useSession', () => ({ useSession: () => ({ user: session.user }) }))

type Call = { method: string; path: string; body: unknown }

function json(body: unknown, status = 200, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json', ...headers } })
}

const request = {
  id: 'r1',
  clinic_id: 'c1',
  patient_id: 'p1',
  patient_name: 'Ana Paciente',
  preferred_start: '2031-05-10T10:00:00Z',
  reason: 'Dor de cabeça',
  status: 'pending',
  appointment_id: null,
  decided_at: null,
  created_at: '2031-05-01T10:00:00Z',
}

function setup(handler: (method: string, path: string, body: unknown) => Response | undefined) {
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
  render(<QueryClientProvider client={client}><AppointmentRequestsPanel /></QueryClientProvider>)
  return calls
}

afterEach(() => vi.unstubAllGlobals())

describe('AppointmentRequestsPanel — patient', () => {
  it('submits only time and reason, then shows the pending request', async () => {
    session.user = { id: 'u1', role: 'patient', staff_role: null }
    let listed: unknown[] = []
    const calls = setup((method) => {
      if (method === 'GET') return json(listed, 200, { 'X-Total-Count': String(listed.length) })
      listed = [request]
      return json(request, 201)
    })
    expect(await screen.findByText('Ainda não fez pedidos de consulta.')).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Data e hora pretendidas'), '2031-05-10T10:00')
    await userEvent.type(screen.getByLabelText('Motivo (opcional)'), 'Dor de cabeça')
    await userEvent.click(screen.getByRole('button', { name: 'Enviar pedido' }))

    const list = await screen.findByRole('list', { name: 'Os meus pedidos de consulta' })
    expect(within(list).getByText('Pendente')).toBeInTheDocument()
    const sent = calls.find((c) => c.method === 'POST')?.body as Record<string, unknown>
    expect(Object.keys(sent).sort()).toEqual(['preferred_start', 'reason'])
    expect(sent.preferred_start).toMatch(/Z$/)
  })

  it('requires a date and shows backend refusals', async () => {
    session.user = { id: 'u1', role: 'patient', staff_role: null }
    const calls = setup((method) =>
      method === 'GET' ? json([], 200, { 'X-Total-Count': '0' }) : json({ detail: 'Tem demasiados pedidos pendentes. Aguarde a resposta da clínica.' }, 409),
    )
    await screen.findByText('Ainda não fez pedidos de consulta.')
    await userEvent.click(screen.getByRole('button', { name: 'Enviar pedido' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Escolha a data e hora pretendidas.')
    expect(calls.filter((c) => c.method === 'POST')).toHaveLength(0)
    await userEvent.type(screen.getByLabelText('Data e hora pretendidas'), '2031-05-10T10:00')
    await userEvent.click(screen.getByRole('button', { name: 'Enviar pedido' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Tem demasiados pedidos pendentes')
  })

  it('cancels a pending request and shows final statuses without actions', async () => {
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
    const list = await screen.findByRole('list', { name: 'Os meus pedidos de consulta' })
    expect(within(list).getByText('Recusado')).toBeInTheDocument()
    expect(within(list).getByText('Aceite')).toBeInTheDocument()
    expect(within(list).getAllByRole('button', { name: 'Cancelar pedido' })).toHaveLength(1)
    await userEvent.click(within(list).getByRole('button', { name: 'Cancelar pedido' }))
    await waitFor(() => expect(within(list).getByText('Cancelado')).toBeInTheDocument())
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
    expect(sent).toEqual({ staff_id: 's1', scheduled_at: expect.stringMatching(/Z$/), duration_minutes: 30 })
    expect(calls.some((c) => c.method === 'GET' && c.path.includes('status=pending'))).toBe(true)
  })

  it('shows a conflict when the request was already processed, and rejects', async () => {
    session.user = { id: 'u8', role: 'staff', staff_role: 'doctor' }
    let listed: unknown[] = [request]
    setup((method, path) => {
      if (path.startsWith('/api/v1/staff')) return json(staffList)
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
})
