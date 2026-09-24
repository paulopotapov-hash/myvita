import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { ApiError, NetworkError } from '../lib/apiClient'
import { authService } from '../services/auth'
import { useSession } from './useSession'

vi.mock('../services/auth')

function renderSession() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return renderHook(() => useSession(), {
    wrapper: ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    ),
  })
}

describe('useSession', () => {
  it('moves from loading to an authenticated restored session', async () => {
    let resolve!: (value: Awaited<ReturnType<typeof authService.me>>) => void
    vi.mocked(authService.me).mockReturnValue(new Promise((done) => (resolve = done)))
    const { result } = renderSession()
    expect(result.current.isLoading).toBe(true)

    resolve({ id: 'u1', email: 'a@b.pt', full_name: 'Ana', role: 'patient', clinic_id: 'c1' })
    await waitFor(() => expect(result.current.isAuthenticated).toBe(true))
    expect(result.current.user?.id).toBe('u1')
  })

  it('distinguishes an invalid session from temporary network and server errors', async () => {
    vi.mocked(authService.me).mockRejectedValueOnce(new ApiError(401, 'unauthorized'))
    const unauthenticated = renderSession()
    await waitFor(() => expect(unauthenticated.result.current.isUnauthenticated).toBe(true))
    unauthenticated.unmount()

    vi.mocked(authService.me).mockRejectedValueOnce(new NetworkError())
    const network = renderSession()
    await waitFor(() => expect(network.result.current.isServerError).toBe(true))
    expect(network.result.current.isUnauthenticated).toBe(false)
    network.unmount()

    vi.mocked(authService.me).mockRejectedValueOnce(new ApiError(503, 'unavailable'))
    const server = renderSession()
    await waitFor(() => expect(server.result.current.isServerError).toBe(true))
    expect(server.result.current.isUnauthenticated).toBe(false)
  })
})
