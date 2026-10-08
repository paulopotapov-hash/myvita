import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { PatientInvitationsPanel } from './PatientInvitationsPanel'

type Call = { method: string; path: string; body: unknown }

function json(body: unknown, status = 200, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json', ...headers } })
}

const pendingInvitation = {
  id: 'inv-1',
  clinic_id: 'clinic-1',
  email: 'ana@example.pt',
  full_name: 'Ana Convidada',
  role: 'patient',
  staff_role: null,
  status: 'pending',
  expires_at: '2099-01-01T10:00:00Z',
  created_at: '2026-10-08T10:00:00Z',
}

function setup(handler: (method: string, path: string, body: unknown) => Response | undefined) {
  const calls: Call[] = []
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), 'http://localhost')
    const method = init?.method ?? 'GET'
    const body = init?.body ? JSON.parse(String(init.body)) : undefined
    calls.push({ method, path: url.pathname + url.search, body })
    const response = handler(method, url.pathname + url.search, body)
    if (!response) throw new Error(`unexpected ${method} ${url.pathname}`)
    return response
  }))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><PatientInvitationsPanel /></QueryClientProvider>)
  return calls
}

afterEach(() => vi.unstubAllGlobals())

describe('PatientInvitationsPanel', () => {
  it('creates an invitation, shows the one-time fragment link and refreshes the pending list', async () => {
    let listed: unknown[] = []
    const calls = setup((method, path) => {
      if (method === 'GET' && path.startsWith('/api/v1/invitations')) return json(listed, 200, { 'X-Total-Count': String(listed.length) })
      if (method === 'POST' && path === '/api/v1/invitations/patients') {
        listed = [pendingInvitation]
        return json({ ...pendingInvitation, token: 'secret-token/with+chars' }, 201)
      }
      return undefined
    })
    expect(await screen.findByText('Não há convites de pacientes pendentes.')).toBeInTheDocument()

    await userEvent.type(screen.getByLabelText('Nome completo'), 'Ana Convidada')
    await userEvent.type(screen.getByLabelText('Email'), 'ana@example.pt')
    await userEvent.click(screen.getByRole('button', { name: 'Criar convite' }))

    const link = await screen.findByLabelText('Link do convite')
    expect(link).toHaveValue(`${window.location.origin}/convite#token=${encodeURIComponent('secret-token/with+chars')}`)
    // Only name and email are sent: clinic/patient identity is decided server-side.
    expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ full_name: 'Ana Convidada', email: 'ana@example.pt' })
    const list = await screen.findByRole('list', { name: 'Convites pendentes' })
    expect(within(list).getByText('Ana Convidada')).toBeInTheDocument()
    // The token never appears in the pending list.
    expect(within(list).queryByText(/secret-token/)).not.toBeInTheDocument()
    expect(window.localStorage.length + window.sessionStorage.length).toBe(0)
  })

  it('validates input before calling the API', async () => {
    const calls = setup((method) => (method === 'GET' ? json([], 200, { 'X-Total-Count': '0' }) : undefined))
    await screen.findByText('Não há convites de pacientes pendentes.')
    await userEvent.type(screen.getByLabelText('Email'), 'not-an-email')
    await userEvent.click(screen.getByRole('button', { name: 'Criar convite' }))
    expect(await screen.findByText('Nome demasiado curto.')).toBeInTheDocument()
    expect(calls.filter((c) => c.method === 'POST')).toHaveLength(0)
  })

  it('shows backend refusals such as an existing account', async () => {
    setup((method) => (method === 'GET' ? json([], 200, { 'X-Total-Count': '0' }) : json({ detail: 'Já existe uma conta com este email.' }, 409)))
    await screen.findByText('Não há convites de pacientes pendentes.')
    await userEvent.type(screen.getByLabelText('Nome completo'), 'Ana Convidada')
    await userEvent.type(screen.getByLabelText('Email'), 'ana@example.pt')
    await userEvent.click(screen.getByRole('button', { name: 'Criar convite' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Já existe uma conta com este email.')
    expect(screen.queryByLabelText('Link do convite')).not.toBeInTheDocument()
  })

  it('revokes a pending invitation and surfaces failures', async () => {
    let listed: unknown[] = [pendingInvitation]
    let revokeAttempts = 0
    const calls = setup((method, path) => {
      if (method === 'GET') return json(listed, 200, { 'X-Total-Count': String(listed.length) })
      if (path === '/api/v1/invitations/inv-1/revoke') {
        revokeAttempts += 1
        if (revokeAttempts === 1) return json({ detail: 'O convite já não está pendente.' }, 409)
        listed = []
        return json({ ...pendingInvitation, status: 'revoked' })
      }
      return undefined
    })
    const revokeButton = await screen.findByRole('button', { name: 'Revogar convite de Ana Convidada' })
    await userEvent.click(revokeButton)
    expect(await screen.findByRole('alert')).toHaveTextContent('O convite já não está pendente.')
    await userEvent.click(revokeButton)
    await waitFor(() => expect(screen.getByText('Não há convites de pacientes pendentes.')).toBeInTheDocument())
    expect(calls.filter((c) => c.path === '/api/v1/invitations/inv-1/revoke')).toHaveLength(2)
  })
})
