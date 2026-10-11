import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { PatientLayout } from './PatientLayout'
import { authService } from '../services/auth'
import { messagesService } from '../services/messages'
import { notificationsService } from '../services/notifications'
import type { ConversationPublic } from '../types/api'

vi.mock('../services/auth')
vi.mock('../services/messages')
vi.mock('../services/notifications')
vi.mock('../hooks/useAuthMutations', () => ({
  useLogout: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
}))

function conversation(id: string, unread: number): ConversationPublic {
  return {
    id, clinic_id: null, patient_id: null, staff_id: null, patient_name: 'Ana', staff_name: 'Dr. Rui',
    status: 'open', closed_at: null, unread_count: unread, can_reply: true, team: null,
    created_at: '2026-10-01T09:00:00Z', updated_at: '2026-10-01T09:00:00Z',
  }
}

function renderPatientShell() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/patient']}>
        <Routes>
          <Route path="/patient" element={<PatientLayout />}>
            <Route index element={<h1>Início do paciente</h1>} />
            <Route path="mensagens" element={<h1>Mensagens do paciente</h1>} />
            <Route path="perfil" element={<h1>Perfil do paciente</h1>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.mocked(authService.me).mockResolvedValue({
    id: '1', email: 'ana@example.pt', full_name: 'Ana Maria Silva', role: 'patient',
    clinic_id: 'c1', staff_role: null, patient_id: 'p1',
  })
  vi.mocked(notificationsService.unreadCount).mockResolvedValue({ count: 0 })
  vi.mocked(messagesService.list).mockResolvedValue({ items: [], total: 0 })
})

describe('header and navigation drawer', () => {
  it('shows the logo as a home link and the avatar with the user initials', async () => {
    renderPatientShell()
    const account = await screen.findByRole('button', { name: 'Menu da conta' })
    expect(account).toHaveTextContent('AS')
    expect(screen.getByRole('link', { name: /myVita\s*, página inicial/ })).toHaveAttribute('href', '/patient')
  })

  it('opens the drawer as a modal dialog and closes it when a section is chosen', async () => {
    const user = userEvent.setup()
    renderPatientShell()
    const toggle = await screen.findByRole('button', { name: 'Menu de navegação' })
    await user.click(toggle)
    const drawer = screen.getByRole('dialog', { name: 'Menu' })
    expect(drawer).toHaveAttribute('aria-modal', 'true')
    expect(within(drawer).getByRole('button', { name: 'Fechar menu' })).toHaveFocus()
    await user.click(within(drawer).getByRole('link', { name: 'Mensagens' }))
    expect(await screen.findByRole('heading', { name: 'Mensagens do paciente' })).toBeInTheDocument()
    expect(screen.queryByRole('dialog', { name: 'Menu' })).not.toBeInTheDocument()
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
  })

  it('closes the drawer on a tap outside it and on the close button, returning focus to ☰', async () => {
    const user = userEvent.setup()
    const { container } = renderPatientShell()
    const toggle = await screen.findByRole('button', { name: 'Menu de navegação' })
    await user.click(toggle)
    const backdrop = container.ownerDocument.querySelector('.bg-slate-900\\/40') as HTMLElement
    await user.click(backdrop)
    expect(screen.queryByRole('dialog', { name: 'Menu' })).not.toBeInTheDocument()
    expect(toggle).toHaveFocus()

    await user.click(toggle)
    await user.click(screen.getByRole('button', { name: 'Fechar menu' }))
    expect(screen.queryByRole('dialog', { name: 'Menu' })).not.toBeInTheDocument()
    expect(toggle).toHaveFocus()
  })

  it('keeps keyboard focus inside the open drawer', async () => {
    const user = userEvent.setup()
    renderPatientShell()
    await user.click(await screen.findByRole('button', { name: 'Menu de navegação' }))
    const drawer = screen.getByRole('dialog', { name: 'Menu' })
    const focusable = within(drawer).getAllByRole('link')
    focusable[focusable.length - 1].focus()
    await user.tab()
    expect(within(drawer).getByRole('button', { name: 'Fechar menu' })).toHaveFocus()
    await user.tab({ shift: true })
    expect(focusable[focusable.length - 1]).toHaveFocus()
  })
})

describe('account menu', () => {
  it('offers Perfil, Segurança and Sair, and closes on Escape or after choosing', async () => {
    const user = userEvent.setup()
    renderPatientShell()
    const account = await screen.findByRole('button', { name: 'Menu da conta' })
    expect(account).toHaveAttribute('aria-expanded', 'false')
    await user.click(account)
    expect(account).toHaveAttribute('aria-expanded', 'true')
    const panel = document.getElementById('account-menu') as HTMLElement
    expect(within(panel).getByText('Ana Maria Silva')).toBeInTheDocument()
    expect(within(panel).getByText('Área do paciente')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sair' })).toBeInTheDocument()
    await user.keyboard('{Escape}')
    expect(account).toHaveAttribute('aria-expanded', 'false')
    expect(account).toHaveFocus()

    await user.click(account)
    await user.click(screen.getByRole('link', { name: 'Perfil' }))
    expect(await screen.findByRole('heading', { name: 'Perfil do paciente' })).toBeInTheDocument()
    expect(account).toHaveAttribute('aria-expanded', 'false')
    expect(document.title).toBe('Perfil · myVita')
  })
})

describe('unread badges', () => {
  it('counts conversations with unread messages, not messages, and unread notifications', async () => {
    vi.mocked(messagesService.list).mockResolvedValue({
      items: [conversation('a', 5), conversation('b', 1), conversation('c', 0)],
      total: 3,
    })
    vi.mocked(notificationsService.unreadCount).mockResolvedValue({ count: 120 })
    const user = userEvent.setup()
    renderPatientShell()
    const toggle = await screen.findByRole('button', { name: 'Menu de navegação' })
    expect(await screen.findByText('Tem itens por ler')).toBeInTheDocument()
    expect(toggle).toHaveAccessibleDescription('Tem itens por ler')
    await user.click(toggle)
    const drawer = screen.getByRole('dialog', { name: 'Menu' })
    expect(within(drawer).getByRole('link', { name: 'Mensagens, 2 conversas por ler' })).toBeInTheDocument()
    // Large counts are capped visually; the screen-reader text keeps the number.
    const notifications = within(drawer).getByRole('link', { name: 'Notificações, 120 notificações por ler' })
    expect(notifications).toHaveTextContent('99+')
    expect(vi.mocked(messagesService.list)).toHaveBeenCalledWith(1, 100, expect.anything(), expect.anything())
  })

  it('shows no badge or menu dot when nothing is unread', async () => {
    renderPatientShell()
    const toggle = await screen.findByRole('button', { name: 'Menu de navegação' })
    expect(toggle).not.toHaveAccessibleDescription()
    expect(screen.queryByText('Tem itens por ler')).not.toBeInTheDocument()
  })
})
