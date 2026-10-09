import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MessagesInboxPage } from './MessagesInboxPage'
import { DOCTOR_USER, PATIENT_USER, conversation, json, mockFetch, renderAt } from './messagesTestUtils'

const session = vi.hoisted(() => ({ user: null as unknown }))
vi.mock('../../hooks/useSession', () => ({ useSession: () => ({ user: session.user }) }))

const routes = (
  <>
    <Route path="/patient/mensagens" element={<MessagesInboxPage />} />
    <Route path="/patient/mensagens/:conversationId" element={<p>Conversa aberta</p>} />
    <Route path="/app/mensagens" element={<MessagesInboxPage />} />
    <Route path="/app/mensagens/:conversationId" element={<p>Conversa aberta</p>} />
  </>
)

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('MessagesInboxPage', () => {
  it('shows a loading state while conversations load', () => {
    session.user = PATIENT_USER
    mockFetch(() => new Promise<Response>(() => {}))
    renderAt('/patient/mensagens', routes)
    expect(screen.getByText('A carregar conversas…')).toBeInTheDocument()
  })

  it('renders conversations with the other participant and unread state', async () => {
    session.user = PATIENT_USER
    const calls = mockFetch((url) =>
      url.pathname === '/api/v1/conversations'
        ? json(
            [
              conversation({ id: 'c-unread', staff_name: 'Dr. Rui', unread_count: 2 }),
              conversation({ id: 'c-read', staff_name: 'Enf. Marta', unread_count: 0 }),
            ],
            200,
            { 'X-Total-Count': '2' },
          )
        : undefined,
    )
    renderAt('/patient/mensagens', routes)

    const unreadLink = await screen.findByRole('link', { name: /Dr\. Rui/ })
    expect(unreadLink).toHaveAttribute('href', '/patient/mensagens/c-unread')
    // Unread is conveyed as text, not only by colour.
    expect(within(unreadLink).getByText('2 não lidas')).toBeInTheDocument()
    const readLink = screen.getByRole('link', { name: /Enf\. Marta/ })
    expect(within(readLink).getByText('Sem mensagens por ler')).toBeInTheDocument()
    // The patient's own name is never shown as "the other participant".
    expect(screen.queryByText('Ana Paciente')).not.toBeInTheDocument()
    expect(calls[0].path).toBe('/api/v1/conversations?page=1&page_size=20')
  })

  it('shows the patient name to staff', async () => {
    session.user = DOCTOR_USER
    mockFetch(() => json([conversation({ patient_name: 'Ana Paciente' })], 200, { 'X-Total-Count': '1' }))
    renderAt('/app/mensagens', routes)
    expect(await screen.findByRole('link', { name: /Ana Paciente/ })).toHaveAttribute('href', '/app/mensagens/conv-1')
  })

  it('shows an empty state without fabricated conversations', async () => {
    session.user = PATIENT_USER
    mockFetch(() => json([], 200, { 'X-Total-Count': '0' }))
    renderAt('/patient/mensagens', routes)
    expect(await screen.findByText('Ainda não tem conversas')).toBeInTheDocument()
    expect(screen.queryAllByRole('link')).toHaveLength(0)
  })

  it('shows a safe error and retries', async () => {
    session.user = PATIENT_USER
    let attempts = 0
    mockFetch(() => {
      attempts += 1
      return attempts === 1
        ? json({ detail: 'Traceback (most recent call last)' }, 500)
        : json([], 200, { 'X-Total-Count': '0' })
    })
    renderAt('/patient/mensagens', routes)
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Ocorreu um erro no servidor')
    expect(alert).not.toHaveTextContent('Traceback')
    await userEvent.click(within(alert).getByRole('button', { name: 'Tentar novamente' }))
    expect(await screen.findByText('Ainda não tem conversas')).toBeInTheDocument()
  })

  it('pages through conversations using the backend pagination', async () => {
    session.user = PATIENT_USER
    const calls = mockFetch((url) =>
      json(
        [conversation({ id: `c-${url.searchParams.get('page')}`, staff_name: `Página ${url.searchParams.get('page')}` })],
        200,
        { 'X-Total-Count': '25' },
      ),
    )
    renderAt('/patient/mensagens', routes)
    await screen.findByText('Página 1')
    await userEvent.click(screen.getByRole('button', { name: 'Seguinte' }))
    expect(await screen.findByText('Página 2')).toBeInTheDocument()
    expect(calls.at(-1)?.path).toBe('/api/v1/conversations?page=2&page_size=20')
  })

  it('does not call the API for roles that cannot message', () => {
    session.user = { ...DOCTOR_USER, role: 'clinic_admin', staff_role: null }
    const calls = mockFetch(() => undefined)
    renderAt('/app/mensagens', routes)
    expect(screen.getByText('Mensagens não disponíveis para o seu perfil')).toBeInTheDocument()
    expect(calls).toHaveLength(0)
  })

  it('never offers patients a way to start a conversation, nor loads the staff roster (M4)', async () => {
    session.user = PATIENT_USER
    const calls = mockFetch((url) => {
      if (url.pathname === '/api/v1/conversations') return json([], 200, { 'X-Total-Count': '0' })
      return undefined
    })
    renderAt('/patient/mensagens', routes)
    expect(await screen.findByText('Ainda não tem conversas')).toBeInTheDocument()
    expect(screen.getByText(/equipa clínica inicia as conversas/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Nova conversa' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Profissional')).not.toBeInTheDocument()
    expect(calls.some((call) => call.method === 'POST')).toBe(false)
    expect(calls.some((call) => call.path.startsWith('/api/v1/staff'))).toBe(false)
  })

  it('lets staff search patients and start a conversation, surfacing backend refusals', async () => {
    session.user = DOCTOR_USER
    let createAttempts = 0
    const calls = mockFetch((url, init) => {
      if (url.pathname === '/api/v1/conversations' && init?.method === 'POST') {
        createAttempts += 1
        return createAttempts === 1
          ? json({ detail: 'Paciente não encontrado.' }, 404)
          : json(conversation({ id: 'new-conv' }), 201)
      }
      if (url.pathname === '/api/v1/conversations') return json([], 200, { 'X-Total-Count': '0' })
      if (url.pathname === '/api/v1/patients') {
        return json(
          [
            { id: 'patient-1', clinic_id: 'clinic-1', full_name: 'Ana Paciente', is_active: true },
            { id: 'patient-9', clinic_id: 'clinic-1', full_name: 'Ana Inativa', is_active: false },
          ],
          200,
          { 'X-Total-Count': '2' },
        )
      }
      return undefined
    })
    renderAt('/app/mensagens', routes)
    await userEvent.click(await screen.findByRole('button', { name: 'Nova conversa' }))
    await userEvent.type(screen.getByLabelText('Pesquisar paciente'), 'Ana')
    await userEvent.click(screen.getByRole('button', { name: 'Pesquisar' }))
    const start = await screen.findByRole('button', { name: 'Iniciar conversa com Ana Paciente' })
    expect(screen.queryByText('Ana Inativa')).not.toBeInTheDocument()
    expect(calls.some((call) => call.path.startsWith('/api/v1/patients?search=Ana'))).toBe(true)

    await userEvent.click(start)
    expect(await screen.findByRole('alert')).toHaveTextContent('Paciente não encontrado.')
    await userEvent.click(start)
    await waitFor(() => expect(screen.getByText('Conversa aberta')).toBeInTheDocument())
    expect(calls.filter((call) => call.method === 'POST').at(-1)?.body).toEqual({ patient_id: 'patient-1' })
  })
})
