import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MESSAGE_MAX_LENGTH } from '../../types/api'
import { ConversationPage } from './ConversationPage'
import { DOCTOR_USER, PATIENT_USER, conversation, json, message, mockFetch, renderAt } from './messagesTestUtils'
import type { MessagePublic } from '../../types/api'

const session = vi.hoisted(() => ({ user: null as unknown }))
vi.mock('../../hooks/useSession', () => ({ useSession: () => ({ user: session.user }) }))

const routes = (
  <>
    <Route path="/patient/mensagens/:conversationId" element={<ConversationPage />} />
    <Route path="/app/mensagens/:conversationId" element={<ConversationPage />} />
  </>
)

afterEach(() => {
  vi.unstubAllGlobals()
})

/** In-memory backend for one conversation, following the real API's rules. */
function fakeBackend(options: { currentUserId: string; messages?: MessagePublic[]; sendStatus?: number } = { currentUserId: PATIENT_USER.id }) {
  const messages = [...(options.messages ?? [])]
  const calls = mockFetch((url, init) => {
    const method = init?.method ?? 'GET'
    if (url.pathname === '/api/v1/conversations/conv-1' && method === 'GET') {
      const page = Number(url.searchParams.get('page'))
      const size = Number(url.searchParams.get('page_size'))
      const newestFirst = [...messages].reverse()
      const unread = messages.filter((m) => m.sender_user_id !== options.currentUserId && !m.read_at).length
      return json(
        { ...conversation({ unread_count: unread }), messages: newestFirst.slice((page - 1) * size, page * size) },
        200,
        { 'X-Total-Count': String(messages.length) },
      )
    }
    if (url.pathname === '/api/v1/conversations/conv-1/read' && method === 'POST') {
      let updated = 0
      for (const m of messages) {
        if (m.sender_user_id !== options.currentUserId && !m.read_at) {
          m.read_at = '2026-10-03T09:00:00Z'
          updated += 1
        }
      }
      return json({ updated_count: updated })
    }
    if (url.pathname === '/api/v1/conversations/conv-1/messages' && method === 'POST') {
      if (options.sendStatus) return json({ detail: 'Demasiados pedidos' }, options.sendStatus)
      const body = JSON.parse(String(init?.body)).body as string
      const created = message({ id: `msg-${messages.length + 1}`, body, sender_user_id: options.currentUserId, created_at: '2026-10-03T10:00:00Z' })
      messages.push(created)
      return json(created, 201)
    }
    return undefined
  })
  return { calls, messages }
}

describe('ConversationPage', () => {
  it('shows a loading state', () => {
    session.user = PATIENT_USER
    mockFetch(() => new Promise<Response>(() => {}))
    renderAt('/patient/mensagens/conv-1', routes)
    expect(screen.getByText('A carregar conversa…')).toBeInTheDocument()
  })

  it('renders history oldest-first and distinguishes own messages from the other participant', async () => {
    session.user = PATIENT_USER
    fakeBackend({
      currentUserId: PATIENT_USER.id,
      messages: [
        message({ id: 'm1', body: 'Bom dia, como se sente?', sender_user_id: DOCTOR_USER.id, read_at: '2026-10-02T10:00:00Z' }),
        message({ id: 'm2', body: 'Melhor, obrigado.', sender_user_id: PATIENT_USER.id, created_at: '2026-10-02T11:00:00Z' }),
      ],
    })
    renderAt('/patient/mensagens/conv-1', routes)

    expect(await screen.findByRole('heading', { name: 'Dr. Rui' })).toBeInTheDocument()
    const items = within(screen.getByRole('list', { name: 'Mensagens' })).getAllByRole('article')
    expect(items.map((item) => item.getAttribute('aria-label'))).toEqual([
      'Mensagem de Dr. Rui',
      'Mensagem enviada por si',
    ])
    expect(within(items[0]).getByText('Bom dia, como se sente?')).toBeInTheDocument()
    expect(within(items[1]).getByText('Você')).toBeInTheDocument()
    expect(within(items[1]).getByText(/Enviada/)).toBeInTheDocument()
  })

  it('shows an empty state for a conversation without messages and does not mark anything read', async () => {
    session.user = DOCTOR_USER
    const { calls } = fakeBackend({ currentUserId: DOCTOR_USER.id })
    renderAt('/app/mensagens/conv-1', routes)
    expect(await screen.findByText('Ainda não há mensagens')).toBeInTheDocument()
    expect(screen.getByText('Conversa com o paciente Ana Paciente')).toBeInTheDocument()
    expect(calls.some((call) => call.path.endsWith('/read'))).toBe(false)
  })

  it('marks incoming messages as read when opened and updates the unread state', async () => {
    session.user = PATIENT_USER
    const { calls, messages } = fakeBackend({
      currentUserId: PATIENT_USER.id,
      messages: [
        message({ id: 'm1', body: 'Nova indicação', sender_user_id: DOCTOR_USER.id }),
        message({ id: 'm2', body: 'Minha mensagem', sender_user_id: PATIENT_USER.id }),
      ],
    })
    renderAt('/patient/mensagens/conv-1', routes)
    await screen.findByText('Nova indicação')
    await waitFor(() => expect(calls.filter((call) => call.path === '/api/v1/conversations/conv-1/read')).toHaveLength(1))
    // Only the doctor's message changed; the patient's own message is untouched.
    expect(messages.find((m) => m.id === 'm1')?.read_at).not.toBeNull()
    expect(messages.find((m) => m.id === 'm2')?.read_at).toBeNull()
    // The detail is refetched after marking read, and no further read call follows.
    await waitFor(() => expect(calls.filter((call) => call.path.startsWith('/api/v1/conversations/conv-1?'))).toHaveLength(2))
    expect(calls.filter((call) => call.path.endsWith('/read'))).toHaveLength(1)
  })

  it('treats 403 and 404 identically without revealing anything about the conversation', async () => {
    for (const status of [403, 404]) {
      session.user = PATIENT_USER
      mockFetch(() => json({ detail: 'Conversa não encontrada.' }, status))
      const { unmount } = renderAt('/patient/mensagens/conv-secret', routes)
      expect(await screen.findByText('Conversa não encontrada')).toBeInTheDocument()
      expect(screen.getByText('Esta conversa não existe ou não tem acesso a ela.')).toBeInTheDocument()
      expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
      expect(screen.getByRole('link', { name: '← Voltar às mensagens' })).toHaveAttribute('href', '/patient/mensagens')
      unmount()
      vi.unstubAllGlobals()
    }
  })

  it('shows a retryable error for server failures', async () => {
    session.user = PATIENT_USER
    mockFetch(() => json({ detail: 'boom' }, 500))
    renderAt('/patient/mensagens/conv-1', routes)
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Ocorreu um erro no servidor')
    expect(within(alert).getByRole('button', { name: 'Tentar novamente' })).toBeInTheDocument()
  })

  it('prevents empty and whitespace-only messages', async () => {
    session.user = PATIENT_USER
    const { calls } = fakeBackend({ currentUserId: PATIENT_USER.id })
    renderAt('/patient/mensagens/conv-1', routes)
    const textbox = await screen.findByLabelText('Mensagem')
    const sendButton = screen.getByRole('button', { name: 'Enviar' })
    expect(sendButton).toBeDisabled()
    await userEvent.type(textbox, '   ')
    expect(sendButton).toBeDisabled()
    await userEvent.type(textbox, '{Control>}{Enter}{/Control}')
    expect(await screen.findByRole('alert')).toHaveTextContent('Escreva uma mensagem antes de enviar.')
    expect(calls.some((call) => call.method === 'POST')).toBe(false)
    expect(textbox).toHaveAttribute('maxLength', String(MESSAGE_MAX_LENGTH))
  })

  it('sends a trimmed message, clears the composer and shows it in the thread', async () => {
    session.user = PATIENT_USER
    const { calls } = fakeBackend({ currentUserId: PATIENT_USER.id })
    renderAt('/patient/mensagens/conv-1', routes)
    const textbox = await screen.findByLabelText('Mensagem')
    await userEvent.type(textbox, '  Tenho uma dúvida  ')
    await userEvent.click(screen.getByRole('button', { name: 'Enviar' }))

    expect(await screen.findByText('Tenho uma dúvida')).toBeInTheDocument()
    expect(textbox).toHaveValue('')
    expect(calls.find((call) => call.method === 'POST')?.body).toEqual({ body: 'Tenho uma dúvida' })
  })

  it('keeps the draft and shows a safe error when sending fails', async () => {
    session.user = PATIENT_USER
    fakeBackend({ currentUserId: PATIENT_USER.id, sendStatus: 429 })
    renderAt('/patient/mensagens/conv-1', routes)
    const textbox = await screen.findByLabelText('Mensagem')
    await userEvent.type(textbox, 'Olá')
    await userEvent.click(screen.getByRole('button', { name: 'Enviar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Demasiados pedidos em pouco tempo')
    expect(textbox).toHaveValue('Olá')
  })

  it('loads older messages using backend pages', async () => {
    session.user = PATIENT_USER
    const history = Array.from({ length: 35 }, (_, index) =>
      message({ id: `m${index}`, body: `Mensagem ${index}`, sender_user_id: DOCTOR_USER.id, read_at: '2026-10-02T10:00:00Z' }),
    )
    const { calls } = fakeBackend({ currentUserId: PATIENT_USER.id, messages: history })
    renderAt('/patient/mensagens/conv-1', routes)
    await screen.findByText('Mensagem 34')
    expect(screen.queryByText('Mensagem 0')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Carregar mensagens anteriores' }))
    expect(await screen.findByText('Mensagem 0')).toBeInTheDocument()
    expect(calls.some((call) => call.path === '/api/v1/conversations/conv-1?page=2&page_size=30')).toBe(true)
    expect(screen.queryByRole('button', { name: 'Carregar mensagens anteriores' })).not.toBeInTheDocument()
  })
})
