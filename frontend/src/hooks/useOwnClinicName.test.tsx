import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useOwnClinicName } from './useOwnClinicName'

const { session } = vi.hoisted(() => ({ session: { user: null as { clinic_id: string | null } | null } }))
vi.mock('./useSession', () => ({ useSession: () => session }))

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

describe('useOwnClinicName', () => {
  beforeEach(() => { session.user = { clinic_id: 'clinic-1' } })
  afterEach(() => vi.restoreAllMocks())

  it('reads the own clinic from the detail endpoint, not from the paginated list', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ id: 'clinic-1', name: 'Clínica Centro' }))
    const { result } = renderHook(() => useOwnClinicName(), { wrapper })
    await waitFor(() => expect(result.current).toBe('Clínica Centro'))
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(String(fetchMock.mock.calls[0][0])).toBe('/api/v1/clinics/clinic-1')
  })

  it('returns null without calling the API when there is no clinic', () => {
    session.user = { clinic_id: null }
    const fetchMock = vi.spyOn(globalThis, 'fetch')
    const { result } = renderHook(() => useOwnClinicName(), { wrapper })
    expect(result.current).toBeNull()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('degrades to null when the backend hides the clinic (404)', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ detail: 'Clínica não encontrada.' }, 404))
    const { result } = renderHook(() => useOwnClinicName(), { wrapper })
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    expect(result.current).toBeNull()
  })
})
