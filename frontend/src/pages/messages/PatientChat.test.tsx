import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ConversationPage } from './ConversationPage'
import { MessagesInboxPage } from './MessagesInboxPage'
import { PATIENT_USER, conversation, json, message, mockFetch, renderAt } from './messagesTestUtils'
import type { ConversationPublic, MessagePublic } from '../../types/api'

const session = vi.hoisted(() => ({ user: null as unknown }))
vi.mock('../../hooks/useSession', () => ({ useSession: () => ({ user: session.user }) }))

const routes = (
  <>
    <Route path="/patient/mensagens" element={<MessagesInboxPage />} />
    <Route path="/patient/mensagens/:conversationId" element={<ConversationPage />} />
  </>
)

const today = (hour: number, minute = 0) => {
  const date = new Date()
  date.setHours(hour, minute, 0, 0)
  return date.toISOString()
}
const yesterday = (hour: number) => {
  const date = new Date()
  date.setDate(date.getDate() - 1)
  date.setHours(hour, 0, 0, 0)
  return date.toISOString()
}

function serveThread(messages: MessagePublic[], overrides: Partial<ConversationPublic> = {}) {
  return mockFetch((url, init) => {
    const method = init?.method ?? 'GET'
    if (url.pathname === '/api/v1/conversations/conv-1' && method === 'GET') {
      return json({ ...conversation(overrides), messages: [...messages].reverse() }, 200, { 'X-Total-Count': String(messages.length) })
    }
    if (url.pathname.endsWith('/read')) return json({ updated_count: 0 })
    return undefined
  })
}

let scrollSpy: ReturnType<typeof vi.fn>
beforeEach(() => {
  session.user = PATIENT_USER
  scrollSpy = vi.fn()
  Element.prototype.scrollIntoView = scrollSpy as unknown as typeof Element.prototype.scrollIntoView
})
afterEach(() => {
  vi.unstubAllGlobals()
})

describe('patient conversation (chat style)', () => {
  it('separates days, groups a run of messages under one name, and shows ✓ / ✓✓', async () => {
    serveThread([
      message({ id: 'm1', body: 'Bom dia', created_at: yesterday(9) }),
      message({ id: 'm2', body: 'Como se sente?', created_at: yesterday(9) }),
      message({ id: 'm3', body: 'Melhor, obrigado.', sender_name: 'Ana Paciente', sender_role: 'patient', is_mine: true, read_at: today(8), created_at: today(7, 30) }),
      message({ id: 'm4', body: 'Ainda uma dúvida.', sender_name: 'Ana Paciente', sender_role: 'patient', is_mine: true, read_at: null, created_at: today(8, 15) }),
    ])
    renderAt('/patient/mensagens/conv-1', routes)
    const list = await screen.findByRole('list', { name: 'Mensagens' })
    const rows = within(list).getAllByRole('listitem').map((item) => item.textContent ?? '')
    expect(rows[0]).toBe('Ontem')
    expect(rows.indexOf('Hoje')).toBe(3)

    const bubbles = within(list).getAllByRole('article')
    // The team member's name once per run, not on every bubble.
    expect(within(bubbles[0]).getByText('Dr. Rui · Médico(a)')).toBeInTheDocument()
    expect(within(bubbles[1]).queryByText('Dr. Rui · Médico(a)')).not.toBeInTheDocument()
    expect(within(bubbles[2]).getByText('Lida')).toHaveClass('sr-only')
    expect(within(bubbles[3]).getByText('Enviada')).toHaveClass('sr-only')
    expect(within(bubbles[3]).getByText('08:15')).toBeInTheDocument()
  })

  it('has a header with back, name and a ⋮ menu with the conversation state', async () => {
    serveThread([message({ id: 'm1', created_at: today(9) })], { status: 'waiting_for_team' })
    const user = userEvent.setup()
    renderAt('/patient/mensagens/conv-1', routes)
    expect(await screen.findByRole('heading', { level: 1, name: 'Dr. Rui' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Voltar às mensagens' })).toHaveAttribute('href', '/patient/mensagens')
    const more = screen.getByRole('button', { name: 'Mais opções' })
    await user.click(more)
    const panel = screen.getByRole('region', { name: 'Estado da conversa' })
    expect(panel).toHaveTextContent('Enviada à equipa clínica')
    // Patients cannot close a conversation; only the care team can.
    expect(screen.queryByRole('button', { name: /Encerrar/ })).not.toBeInTheDocument()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('region', { name: 'Estado da conversa' })).not.toBeInTheDocument()
    expect(more).toHaveFocus()
  })

  it('scrolls to the newest message and offers a send button with an accessible name', async () => {
    serveThread([message({ id: 'm1', created_at: today(9) })])
    renderAt('/patient/mensagens/conv-1', routes)
    await screen.findByRole('list', { name: 'Mensagens' })
    expect(scrollSpy).toHaveBeenCalledWith({ block: 'end' })
    expect(screen.getByRole('button', { name: 'Enviar' })).toBeDisabled()
    expect(screen.getByLabelText('Mensagem')).toHaveAttribute('placeholder', 'Escreva uma mensagem')
  })
})

describe('patient conversation list', () => {
  it('shows initials, the relative time and bold unread conversations', async () => {
    mockFetch((url) =>
      url.pathname === '/api/v1/conversations'
        ? json(
            [
              conversation({ id: 'c1', staff_name: 'Rui Costa', unread_count: 3, updated_at: today(9, 5) }),
              conversation({ id: 'c2', staff_name: 'Marta Lima', unread_count: 0, updated_at: yesterday(10) }),
            ],
            200,
            { 'X-Total-Count': '2' },
          )
        : undefined,
    )
    renderAt('/patient/mensagens', routes)
    const unread = await screen.findByRole('link', { name: /Rui Costa/ })
    expect(unread).toHaveTextContent('RC')
    expect(unread).toHaveTextContent('09:05')
    expect(within(unread).getByText('3 mensagens novas')).toHaveClass('font-semibold')
    const read = screen.getByRole('link', { name: /Marta Lima/ })
    expect(read).toHaveTextContent('Ontem')
    expect(read).not.toHaveTextContent('mensagens novas')
  })
})
