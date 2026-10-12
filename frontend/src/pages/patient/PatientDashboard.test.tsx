import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { PatientDashboard } from './PatientDashboard'
import { appointmentsService } from '../../services/appointments'
import { messagesService } from '../../services/messages'
import { notificationsService } from '../../services/notifications'
import type { AppointmentPatientView, ConversationPublic, NotificationPublic } from '../../types/api'

vi.mock('../../services/appointments')
vi.mock('../../services/messages')
vi.mock('../../services/notifications')
vi.mock('../../hooks/useSession', () => ({
  useSession: () => ({
    user: { id: 'u1', email: 'ana@example.pt', full_name: 'Ana Maria Silva', role: 'patient', clinic_id: 'c1', staff_role: null, patient_id: 'p1' },
  }),
}))

const DAY = 86_400_000
const inDays = (days: number) => new Date(Date.now() + days * DAY).toISOString()

function appointment(id: string, days: number, status: AppointmentPatientView['status'], staff = 'Dra. Rita Sousa'): AppointmentPatientView {
  return {
    view: 'patient', id, staff_name: staff, scheduled_at: inDays(days), ends_at: inDays(days), duration_minutes: 30, status, reason: null,
    appointment_type: 'Consulta', specialty: null, location: null, can_change: true, change_until: null, booking_mode: null, patient_confirmed_at: null, can_confirm: true,
  }
}

function conversation(id: string, unread: number, updatedAt: string, staff = 'Dr. Rui'): ConversationPublic {
  return {
    id, clinic_id: null, patient_id: null, staff_id: null, patient_name: 'Ana', staff_name: staff, status: 'waiting_for_patient',
    closed_at: null, unread_count: unread, can_reply: true, team: null, created_at: updatedAt, updated_at: updatedAt,
  }
}

function notification(id: string, overrides: Partial<NotificationPublic>): NotificationPublic {
  return {
    id, title: 'Novo resultado disponível', message: 'Tem um novo resultado.', is_read: false, read_at: null,
    created_at: '2026-10-10T10:00:00Z', target_type: 'result', target_id: null, conversation_target_id: null,
    result_target_id: null, record_target_id: null, ...overrides,
  }
}

function renderHome() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter><PatientDashboard /></MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.mocked(appointmentsService.list).mockResolvedValue([])
  vi.mocked(messagesService.list).mockResolvedValue({ items: [], total: 0 })
  vi.mocked(notificationsService.list).mockResolvedValue({ items: [], total: 0 })
})

describe('PatientDashboard', () => {
  it('greets by first name and shows the six shortcuts in order, without the old buttons', async () => {
    renderHome()
    expect(screen.getByRole('heading', { level: 1, name: 'Olá, Ana!' })).toBeInTheDocument()
    const shortcuts = within(screen.getByRole('navigation', { name: 'Atalhos' })).getAllByRole('link')
    expect(shortcuts.map((link) => [link.textContent, link.getAttribute('href')])).toEqual([
      ['Marcar consulta', '/patient/consultas/marcar'],
      ['Mensagens', '/patient/mensagens'],
      ['Resultados', '/patient/resultados'],
      ['Medicação', '/patient/medicacao'],
      ['Documentos', '/patient/documentos'],
      ['Consultas', '/patient/consultas'],
    ])
    for (const old of ['Ver todas as consultas', 'O meu perfil', 'Os meus resultados', 'Gerir consentimentos', 'Notificações']) {
      expect(screen.queryByRole('link', { name: old })).not.toBeInTheDocument()
    }
    expect(await screen.findByRole('heading', { name: 'Sem consultas marcadas' })).toBeInTheDocument()
  })

  it('counts unread conversations and unopened results on the shortcuts, and highlights them', async () => {
    vi.mocked(messagesService.list).mockResolvedValue({
      items: [
        conversation('c1', 2, '2026-10-10T10:00:00Z'),
        conversation('c2', 0, '2026-10-11T09:00:00Z'),
        conversation('c3', 1, '2026-10-11T08:00:00Z', 'Enf. Sara'),
      ],
      total: 3,
    })
    vi.mocked(notificationsService.list).mockResolvedValue({
      items: [
        notification('n1', { result_target_id: 'r1' }),
        notification('n2', { result_target_id: 'r1' }), // same result twice: counts once
        notification('n3', { result_target_id: 'r2', is_read: true }), // already opened
        notification('n4', { title: 'Novo documento', target_type: 'document', target_id: 'd1' }),
        notification('n5', { result_target_id: 'r3' }),
      ],
      total: 5,
    })
    renderHome()
    expect(await screen.findByRole('link', { name: 'Mensagens, 2 conversas por ler' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Resultados, 2 resultados por abrir' })).toBeInTheDocument()

    const message = screen.getByRole('region', { name: 'Mensagem por ler' })
    expect(message).toHaveTextContent('Conversa com Enf. Sara') // the most recent unread conversation
    expect(message).toHaveTextContent('1 mensagem nova')
    expect(within(message).getByRole('link', { name: 'Ver mensagem' })).toHaveAttribute('href', '/patient/mensagens/c3')

    const results = screen.getByRole('region', { name: 'Resultados por abrir' })
    expect(results).toHaveTextContent('Tem 2 resultados novos')
    expect(within(results).getByRole('link', { name: 'Ver resultados' })).toHaveAttribute('href', '/patient/resultados')
  })

  it('links straight to the result when only one is unopened', async () => {
    vi.mocked(notificationsService.list).mockResolvedValue({ items: [notification('n1', { result_target_id: 'r9' })], total: 1 })
    renderHome()
    const results = await screen.findByRole('region', { name: 'Resultados por abrir' })
    expect(within(results).getByRole('link', { name: 'Ver resultados' })).toHaveAttribute('href', '/patient/resultados?result=r9')
  })

  it('shows the next upcoming appointment with date, time and professional', async () => {
    vi.mocked(appointmentsService.list).mockResolvedValue([
      appointment('past', -1, 'scheduled'),
      appointment('cancelled', 1, 'cancelled', 'Dr. Cancelado'),
      appointment('later', 10, 'scheduled', 'Dr. Mais Tarde'),
      appointment('next', 3, 'confirmed'),
    ])
    renderHome()
    const card = await screen.findByRole('region', { name: 'Próxima consulta' })
    expect(card).toHaveTextContent('Com Dra. Rita Sousa')
    expect(card).toHaveTextContent(/às \d{2}:\d{2}/)
    expect(card).not.toHaveTextContent('Dr. Mais Tarde')
    expect(within(card).getByRole('link', { name: 'Ver detalhes' })).toHaveAttribute('href', '/patient/consultas/next')
  })

  it('offers to book when nothing is scheduled, and hides empty message and result cards', async () => {
    vi.mocked(appointmentsService.list).mockResolvedValue([appointment('past', -2, 'completed')])
    renderHome()
    const empty = await screen.findByRole('region', { name: 'Sem consultas marcadas' })
    expect(within(empty).getByRole('link', { name: 'Marcar consulta' })).toHaveAttribute('href', '/patient/consultas/marcar')
    expect(screen.queryByRole('region', { name: 'Mensagem por ler' })).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Resultados por abrir' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Mensagens' })).toBeInTheDocument() // no badge text
  })

  it('shows a retryable error when appointments fail to load', async () => {
    vi.mocked(appointmentsService.list).mockRejectedValue(new Error('boom'))
    renderHome()
    expect(await screen.findByRole('button', { name: /tentar/i })).toBeInTheDocument()
  })
})
