import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuditLogPage } from './AuditLogPage'
import { ApiError } from '../../lib/apiClient'
import { auditLogQuery } from '../../services/auditLogs'
import type { AuditLogPublic } from '../../types/api'

const { useAuditLogs } = vi.hoisted(() => ({ useAuditLogs: vi.fn() }))
vi.mock('../../hooks/useAuditLogs', () => ({ useAuditLogs }))

const entry: AuditLogPublic = {
  id: 'log-1', timestamp: '2026-09-24T10:00:00Z', actor: { user_id: 'u1', email: 'dr@clinic.pt', name: 'Ana Silva' }, action: 'document_downloaded',
  result: 'success', resource_type: 'document', resource_id: 'doc-1', ip_address: '10.0.0.5', request_id: 'req-1',
  metadata: { patient_id: 'p1' },
}

describe('AuditLogPage', () => {
  beforeEach(() => {
    useAuditLogs.mockReset()
    useAuditLogs.mockReturnValue({ data: { items: [entry], total: 1 }, isLoading: false, isError: false, refetch: vi.fn() })
  })

  it('renders readable actions, actor, resource, timestamp and result', () => {
    render(<AuditLogPage />)
    expect(screen.getByRole('heading', { name: 'Auditoria' })).toBeInTheDocument()
    const item = within(screen.getByRole('list', { name: 'Eventos de auditoria' })).getByRole('listitem')
    expect(item).toHaveTextContent('Documento transferido')
    expect(item).toHaveTextContent('Ana Silva · dr@clinic.pt')
    expect(item).toHaveTextContent('document doc-1')
    expect(item).toHaveTextContent('Sucesso')
    expect(item).toHaveTextContent('patient_id: p1')
  })

  it('falls back to email for deleted actors and to a system label for anonymous events', () => {
    useAuditLogs.mockReturnValue({
      data: {
        total: 2,
        items: [
          { ...entry, id: 'log-2', actor: { user_id: null, email: 'former@clinic.pt', name: null } },
          { ...entry, id: 'log-3', action: 'rate_limited', result: 'denied', actor: { user_id: null, email: null, name: null } },
        ],
      },
      isLoading: false, isError: false, refetch: vi.fn(),
    })
    render(<AuditLogPage />)
    const items = within(screen.getByRole('list', { name: 'Eventos de auditoria' })).getAllByRole('listitem')
    expect(items[0]).toHaveTextContent('former@clinic.pt')
    expect(items[0]).not.toHaveTextContent('Ana Silva')
    expect(items[1]).toHaveTextContent('Sistema / anónimo')
    expect(items[1]).toHaveTextContent('Negado')
  })

  it('shows loading, error and empty states', () => {
    useAuditLogs.mockReturnValueOnce({ data: undefined, isLoading: true, isError: false, refetch: vi.fn() })
    const { unmount } = render(<AuditLogPage />)
    expect(screen.getByText('A carregar auditoria…')).toBeInTheDocument()
    unmount()
    useAuditLogs.mockReturnValueOnce({ data: undefined, isLoading: false, isError: true, error: new ApiError(403, 'HTTP 403'), refetch: vi.fn() })
    const second = render(<AuditLogPage />)
    expect(screen.getByText('Não tens permissão para aceder a este recurso.')).toBeInTheDocument()
    second.unmount()
    useAuditLogs.mockReturnValueOnce({ data: { items: [], total: 0 }, isLoading: false, isError: false, refetch: vi.fn() })
    render(<AuditLogPage />)
    expect(screen.getByText('Sem eventos')).toBeInTheDocument()
  })

  it('applies validated filters and resets to page 1', async () => {
    const user = userEvent.setup()
    render(<AuditLogPage />)
    await user.selectOptions(screen.getByLabelText('Ação'), 'login_failure')
    await user.type(screen.getByLabelText('ID do recurso'), 'not-a-uuid')
    await user.click(screen.getByRole('button', { name: 'Filtrar' }))
    expect(screen.getByRole('alert')).toHaveTextContent('UUIDs válidos')
    expect(useAuditLogs).toHaveBeenLastCalledWith(1, 25, {})

    await user.clear(screen.getByLabelText('ID do recurso'))
    await user.type(screen.getByLabelText('ID do recurso'), '11111111-2222-4333-8444-555555555555')
    await user.click(screen.getByRole('button', { name: 'Filtrar' }))
    expect(useAuditLogs).toHaveBeenLastCalledWith(1, 25, { action: 'login_failure', resourceId: '11111111-2222-4333-8444-555555555555' })
  })

  it('builds the backend query string from filters', () => {
    const query = auditLogQuery(2, 25, { action: 'logout', actorUserId: 'u1', resourceType: 'user', dateFrom: '2026-01-01T00:00' })
    const params = new URLSearchParams(query)
    expect(params.get('page')).toBe('2')
    expect(params.get('action')).toBe('logout')
    expect(params.get('actor_user_id')).toBe('u1')
    expect(params.get('resource_type')).toBe('user')
    expect(params.get('date_from')).toMatch(/Z$/)
    expect(params.has('clinic_id')).toBe(false)
  })
})
