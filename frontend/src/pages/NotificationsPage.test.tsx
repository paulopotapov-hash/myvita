import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { act } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '../lib/apiClient'
import { NotificationsPage } from './NotificationsPage'

const { markRead, markReadState, useNotifications } = vi.hoisted(() => ({
  markRead: vi.fn(),
  markReadState: { isPending: false, variables: undefined as string | undefined },
  useNotifications: vi.fn(),
}))

vi.mock('../hooks/useClinicalData', () => ({
  useNotifications,
  useMarkNotificationRead: () => ({ mutate: markRead, ...markReadState }),
}))

const unread = (id: string) => ({ id, title: `Aviso ${id}`, message: 'Mensagem', is_read: false, read_at: null, created_at: '2026-09-24T10:00:00Z' })

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
    expect(markRead).toHaveBeenCalledWith('n1', expect.objectContaining({ onError: expect.any(Function) }))
    await user.click(screen.getByRole('button', { name: 'Seguinte' }))
    expect(useNotifications).toHaveBeenLastCalledWith(2, 20)
    expect(screen.getByText('Página seguinte')).toBeInTheDocument()
  })

  it('shows an empty state when there are no notifications', () => {
    useNotifications.mockReturnValue({ data: { total: 0, items: [] }, isLoading: false, isError: false })
    render(<NotificationsPage />)
    expect(screen.getByText('Sem notificações')).toBeInTheDocument()
  })

  it('surfaces a mark-as-read failure instead of swallowing it', async () => {
    markRead.mockReset()
    useNotifications.mockReturnValue({ data: { total: 1, items: [unread('n1')] }, isLoading: false, isError: false })
    const user = userEvent.setup()
    render(<NotificationsPage />)
    await user.click(screen.getByRole('button', { name: 'Marcar como lida' }))
    const options = markRead.mock.calls.at(-1)?.[1] as { onError: (error: unknown) => void }
    act(() => options.onError(new ApiError(404, 'Notificação não encontrada.', { detail: 'Notificação não encontrada.' })))
    expect(await screen.findByRole('alert')).toHaveTextContent('Notificação não encontrada.')
  })

  it('locks every action while a request runs and spins only the clicked row', () => {
    markReadState.isPending = true
    markReadState.variables = 'n2'
    useNotifications.mockReturnValue({ data: { total: 2, items: [unread('n1'), unread('n2')] }, isLoading: false, isError: false })
    render(<NotificationsPage />)
    const [first, second] = screen.getAllByRole('button', { name: 'Marcar como lida' })
    expect(first).toBeDisabled()
    expect(second).toBeDisabled()
    expect(first).toHaveAttribute('aria-busy', 'false')
    expect(second).toHaveAttribute('aria-busy', 'true')
    markReadState.isPending = false
    markReadState.variables = undefined
  })
})
