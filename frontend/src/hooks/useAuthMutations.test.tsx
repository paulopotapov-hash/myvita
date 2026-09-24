import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { authService } from '../services/auth'
import { SESSION_QUERY_KEY } from './useSession'
import { useLogin, useLogout } from './useAuthMutations'

vi.mock('../services/auth')

function setup() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  return { queryClient, wrapper }
}

describe('authentication mutations', () => {
  it('confirms a successful login through /me and stores that authoritative user', async () => {
    const { queryClient, wrapper } = setup()
    const loginUser = { id: 'response-user', email: 'a@b.pt', full_name: 'A', role: 'patient' as const, clinic_id: 'c1' }
    const sessionUser = { ...loginUser, id: 'session-user' }
    vi.mocked(authService.login).mockResolvedValue(loginUser)
    vi.mocked(authService.me).mockResolvedValue(sessionUser)
    const { result } = renderHook(() => useLogin(), { wrapper })

    act(() => result.current.mutate({ email: 'a@b.pt', password: 'secret' }))
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(authService.me).toHaveBeenCalledOnce()
    expect(queryClient.getQueryData(SESSION_QUERY_KEY)).toEqual(sessionUser)
  })

  it('clears authenticated data after logout while preserving public cache', async () => {
    const { queryClient, wrapper } = setup()
    queryClient.setQueryData(SESSION_QUERY_KEY, { id: 'u1' })
    queryClient.setQueryData(['appointments'], [{ id: 'a1' }])
    queryClient.setQueryData(['clinics'], [{ id: 'c1' }])
    vi.mocked(authService.logout).mockResolvedValue()
    const { result } = renderHook(() => useLogout(), { wrapper })

    act(() => result.current.mutate())
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(queryClient.getQueryData(SESSION_QUERY_KEY)).toBeNull()
    expect(queryClient.getQueryData(['appointments'])).toBeUndefined()
    expect(queryClient.getQueryData(['clinics'])).toEqual([{ id: 'c1' }])
  })
})
