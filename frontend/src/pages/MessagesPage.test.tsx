import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MessagesPage } from './MessagesPage'

const mocks = vi.hoisted(() => ({
  user: { role: 'patient' as 'patient' | 'staff', staff_role: null as 'doctor' | 'nurse' | null },
  inbox: vi.fn(),
  conversation: vi.fn(),
  patients: vi.fn(),
  start: vi.fn(),
  reply: vi.fn(),
  setStatus: vi.fn(),
  escalate: vi.fn(),
}))

vi.mock('../hooks/useSession', () => ({ useSession: () => ({ user: mocks.user }) }))
vi.mock('../hooks/useClinicData', () => ({ usePatients: (...args: unknown[]) => mocks.patients(...args) }))
vi.mock('../hooks/useMessaging', () => ({
  useConversationInbox: (...args: unknown[]) => mocks.inbox(...args),
  useConversation: (...args: unknown[]) => mocks.conversation(...args),
  useStartConversation: () => ({ mutate: mocks.start, isPending: false }),
  useReplyToConversation: () => ({ mutate: mocks.reply, isPending: false }),
  useUpdateConversationStatus: () => ({ mutate: mocks.setStatus, isPending: false }),
  useEscalateConversation: () => ({ mutate: mocks.escalate, isPending: false }),
}))

const detail = {
  id: 'conversation-1', patient_id: 'patient-1', patient_name: 'Ana Silva', subject: 'Plano de cuidados',
  status: 'waiting_for_patient' as const, needs_doctor_review: false, updated_at: '2026-09-24T10:00:00Z',
  closed_at: null, unread: false,
  last_message: { id: 'message-1', sender_name: 'Dra. Joana', sender_role: 'doctor' as const, body: 'Como está?', created_at: '2026-09-24T10:00:00Z' },
  messages: [
    { id: 'message-1', sender_name: 'Dra. Joana', sender_role: 'doctor' as const, body: 'Como está?', created_at: '2026-09-24T10:00:00Z' },
    { id: 'message-2', sender_name: 'Ana Silva', sender_role: 'patient' as const, body: 'Melhor, obrigada.', created_at: '2026-09-24T10:05:00Z' },
  ],
}

function renderPage(path = '/app/mensagens?conversation=conversation-1') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes><Route path="/app/mensagens" element={<MessagesPage />} /></Routes>
    </MemoryRouter>,
  )
}

describe('MessagesPage', () => {
  beforeEach(() => {
    mocks.user.role = 'patient'
    mocks.user.staff_role = null
    mocks.inbox.mockReturnValue({ data: [detail], isLoading: false, isError: false, refetch: vi.fn() })
    mocks.conversation.mockReturnValue({ data: detail, isLoading: false, isError: false, refetch: vi.fn() })
    mocks.patients.mockReturnValue({ data: [], isLoading: false })
    mocks.start.mockReset()
    mocks.reply.mockReset()
    mocks.setStatus.mockReset()
    mocks.escalate.mockReset()
  })

  it('shows sender name and role and lets a patient reply without a new-conversation control', async () => {
    const user = userEvent.setup()
    renderPage()
    expect(screen.getByText('Dra. Joana')).toBeInTheDocument()
    expect(screen.getByText('Médico', { exact: true })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Nova conversa' })).not.toBeInTheDocument()
    await user.type(screen.getByLabelText('Responder à equipa clínica'), 'Estou melhor.')
    await user.click(screen.getByRole('button', { name: 'Enviar resposta' }))
    expect(mocks.reply).toHaveBeenCalledWith(
      { id: 'conversation-1', body: 'Estou melhor.' },
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
    )
  })

  it('lets clinical staff start a conversation with a first message', async () => {
    mocks.user.role = 'staff'
    mocks.user.staff_role = 'doctor'
    mocks.inbox.mockReturnValue({ data: [], isLoading: false, isError: false, refetch: vi.fn() })
    mocks.conversation.mockReturnValue({ data: undefined, isLoading: false, isError: false })
    mocks.patients.mockReturnValue({ data: [{ id: 'patient-1', full_name: 'Ana Silva' }] })
    const user = userEvent.setup()
    renderPage('/app/mensagens')
    await user.click(screen.getByRole('button', { name: 'Nova conversa' }))
    await user.selectOptions(screen.getByLabelText('Paciente'), 'patient-1')
    await user.type(screen.getByLabelText('Assunto'), 'Plano de cuidados')
    await user.type(screen.getByLabelText('Primeira mensagem'), 'Como está?')
    await user.click(screen.getByRole('button', { name: 'Enviar ao paciente' }))
    expect(mocks.start).toHaveBeenCalledWith(
      { patientId: 'patient-1', subject: 'Plano de cuidados', body: 'Como está?' },
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
    )
  })

  it('shows escalation only to nurses and routes it through the mutation', async () => {
    mocks.user.role = 'staff'
    mocks.user.staff_role = 'nurse'
    const user = userEvent.setup()
    const { unmount } = renderPage()
    await user.click(screen.getByRole('button', { name: 'Escalar a médico' }))
    expect(mocks.escalate).toHaveBeenCalledWith('conversation-1', expect.any(Object))

    unmount()
    mocks.user.staff_role = 'doctor'
    renderPage()
    expect(screen.queryByRole('button', { name: 'Escalar a médico' })).not.toBeInTheDocument()
  })
})
