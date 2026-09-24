import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { NotificationsPage } from './NotificationsPage'

const { markRead, useNotifications } = vi.hoisted(() => ({
  markRead: vi.fn(),
  useNotifications: vi.fn(),
}))

vi.mock('../hooks/useClinicalData', () => ({
  useNotifications,
  useMarkNotificationRead: () => ({ mutate: markRead, isPending: false }),
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
    render(<NotificationsPage />)

    await user.click(screen.getByRole('button', { name: 'Marcar como lida' }))
    expect(markRead).toHaveBeenCalledWith('n1')
    await user.click(screen.getByRole('button', { name: 'Seguinte' }))
    expect(useNotifications).toHaveBeenLastCalledWith(2, 20)
    expect(screen.getByText('Página seguinte')).toBeInTheDocument()
  })
})
