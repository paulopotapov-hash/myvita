import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { NotificationsPage } from './NotificationsPage'

const { markRead, markAllRead, useNotifications } = vi.hoisted(() => ({
  markRead: vi.fn(),
  markAllRead: vi.fn(),
  useNotifications: vi.fn(),
}))

vi.mock('../hooks/useClinicalData', () => ({
  useNotifications,
  useMarkNotificationRead: () => ({ mutate: markRead, isPending: false }),
  useMarkAllNotificationsRead: () => ({ mutate: markAllRead, isPending: false }),
}))
vi.mock('../hooks/useSession', () => ({
  useSession: () => ({ user: { role: 'patient' } }),
}))

describe('NotificationsPage', () => {
  it('marks an unread notification as read and requests the next server page', async () => {
    useNotifications.mockImplementation((page: number) => ({
      data: {
        total: 21,
        items: page === 1
          ? [{ id: 'n1', title: 'Consulta alterada', message: 'Novo horário', is_read: false, read_at: null, created_at: '2026-09-24T10:00:00Z' }]
          : [{ id: 'n2', title: 'Página seguinte', message: 'Mensagem', is_read: true, read_at: '2026-09-24T11:00:00Z', created_at: '2026-09-24T11:00:00Z' }],
      },
      isLoading: false,
      isError: false,
    }))
    const user = userEvent.setup()
    render(<MemoryRouter><NotificationsPage /></MemoryRouter>)

    await user.click(screen.getByRole('button', { name: 'Marcar como lida' }))
    expect(markRead).toHaveBeenCalledWith('n1', expect.objectContaining({ onError: expect.any(Function) }))
    await user.click(screen.getByRole('button', { name: 'Seguinte' }))
    expect(useNotifications).toHaveBeenLastCalledWith(2, 20)
    expect(screen.getByText('Página seguinte')).toBeInTheDocument()
  })

  it('links each notification to its own target (M6, D4)', () => {
    const base = { message: 'Genérica', is_read: false, read_at: null, created_at: '2026-09-24T10:00:00Z' }
    useNotifications.mockReturnValue({
      data: {
        total: 3,
        items: [
          { ...base, id: 'n4', title: 'Nova mensagem', target_type: 'conversation', target_id: null, conversation_target_id: 'conv-9' },
          { ...base, id: 'n5', title: 'Novo documento', target_type: 'document', target_id: 'doc-7', conversation_target_id: null },
          { ...base, id: 'n6', title: 'Consulta', target_type: null, target_id: null, conversation_target_id: null },
        ],
      },
      isLoading: false,
      isError: false,
    })
    render(<MemoryRouter><NotificationsPage /></MemoryRouter>)
    expect(screen.getByRole('link', { name: 'Abrir conversa' })).toHaveAttribute('href', '/patient/mensagens/conv-9')
    expect(screen.getByRole('link', { name: 'Abrir documento' })).toHaveAttribute('href', '/patient/documentos?document=doc-7')
    expect(screen.getByRole('link', { name: 'Abrir consultas' })).toHaveAttribute('href', '/patient/consultas')
  })

  it('marks all visible unread notifications as read', async () => {
    useNotifications.mockReturnValue({
      data: { total: 1, items: [{ id: 'n3', title: 'Consulta', message: 'Atualização', is_read: false, read_at: null, created_at: '2026-09-24T10:00:00Z' }] },
      isLoading: false,
      isError: false,
    })
    const user = userEvent.setup()
    render(<MemoryRouter><NotificationsPage /></MemoryRouter>)

    await user.click(screen.getByRole('button', { name: 'Marcar todas como lidas' }))
    expect(markAllRead).toHaveBeenCalledWith(undefined, expect.objectContaining({ onError: expect.any(Function) }))
  })
})
