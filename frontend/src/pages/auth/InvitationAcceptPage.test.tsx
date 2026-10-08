import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { InvitationAcceptPage } from './InvitationAcceptPage'

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

const preview = {
  clinic_name: 'Clínica Central',
  email: 'ana@example.pt',
  full_name: 'Ana Convidada',
  role: 'patient',
  staff_role: null,
  expires_at: '2099-01-01T10:00:00Z',
}

function renderWithToken(token: string, handler: (path: string, body: unknown) => Response) {
  window.history.replaceState(null, '', `/convite#token=${encodeURIComponent(token)}`)
  const calls: { path: string; body: unknown }[] = []
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = new URL(String(input), 'http://localhost').pathname
    const body = init?.body ? JSON.parse(String(init.body)) : undefined
    calls.push({ path, body })
    return handler(path, body)
  }))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/convite']}><InvitationAcceptPage /></MemoryRouter>
    </QueryClientProvider>,
  )
  return calls
}

afterEach(() => {
  vi.unstubAllGlobals()
  window.history.replaceState(null, '', '/')
})

describe('InvitationAcceptPage', () => {
  it('activates a patient account, removes the token from the URL and continues to the patient area', async () => {
    const token = 'a'.repeat(64)
    const calls = renderWithToken(token, (path) =>
      path.endsWith('/preview')
        ? json(preview)
        : json({ id: 'u1', email: 'ana@example.pt', full_name: 'Ana Convidada', role: 'patient', clinic_id: 'c1', staff_role: null, patient_id: 'p1' }),
    )
    expect(await screen.findByText('Clínica Central')).toBeInTheDocument()
    expect(window.location.hash).toBe('')
    expect(window.location.href).not.toContain(token)

    await userEvent.type(screen.getByLabelText('Nova palavra-passe'), 'PacienteNovo123!')
    await userEvent.type(screen.getByLabelText('Confirmar palavra-passe'), 'PacienteNovo123!')
    await userEvent.click(screen.getByRole('button', { name: 'Ativar conta' }))

    expect(await screen.findByRole('link', { name: 'Continuar' })).toHaveAttribute('href', '/patient')
    // Only the token and password are sent — never a clinic, patient or role.
    expect(calls.find((c) => c.path.endsWith('/accept'))?.body).toEqual({ token, password: 'PacienteNovo123!' })
    expect(window.localStorage.length + window.sessionStorage.length).toBe(0)
  })

  it.each([
    [410, 'Convite já utilizado ou revogado.', 'Convite já utilizado ou revogado.'],
    [410, 'Convite expirado.', 'Convite expirado.'],
    [404, 'Convite inválido.', 'Este convite não é válido.'],
  ])('shows a final state without retry for HTTP %i (%s)', async (status, detail, shown) => {
    renderWithToken('b'.repeat(64), () => json({ detail }, status))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(shown)
    expect(screen.queryByRole('button', { name: 'Tentar novamente' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Ir para o início de sessão' })).toHaveAttribute('href', '/login')
    expect(screen.queryByLabelText('Nova palavra-passe')).not.toBeInTheDocument()
  })

  it('keeps retry for transient server errors', async () => {
    renderWithToken('c'.repeat(64), () => json({ detail: 'boom' }, 503))
    expect(await screen.findByRole('button', { name: 'Tentar novamente' })).toBeInTheDocument()
  })

  it('reports a failed activation without leaving the form', async () => {
    renderWithToken('d'.repeat(64), (path) =>
      path.endsWith('/preview') ? json(preview) : json({ detail: 'Convite já utilizado ou revogado.' }, 410),
    )
    await screen.findByText('Clínica Central')
    await userEvent.type(screen.getByLabelText('Nova palavra-passe'), 'PacienteNovo123!')
    await userEvent.type(screen.getByLabelText('Confirmar palavra-passe'), 'PacienteNovo123!')
    await userEvent.click(screen.getByRole('button', { name: 'Ativar conta' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Convite já utilizado ou revogado.')
  })
})
