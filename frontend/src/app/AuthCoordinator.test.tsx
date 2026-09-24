import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SESSION_QUERY_KEY } from '../hooks/useSession'
import { apiRequest } from '../lib/apiClient'
import { AuthCoordinator } from './AuthCoordinator'

function LoginDestination() {
  const location = useLocation()
  return <div>Login from {(location.state as { from?: string } | null)?.from}</div>
}

afterEach(() => vi.unstubAllGlobals())

describe('AuthCoordinator', () => {
  it('expires a known session on a global 401, clears cache and preserves the current URL', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    queryClient.setQueryData(SESSION_QUERY_KEY, {
      id: 'u1',
      email: 'ana@example.com',
      full_name: 'Ana',
      role: 'patient',
      clinic_id: 'c1',
    })
    queryClient.setQueryData(['appointments'], [{ id: 'a1' }])
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ detail: 'Sessão expirada.' }),
      }),
    )

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/app/consultas?dia=hoje']}>
          <AuthCoordinator />
          <Routes>
            <Route
              path="/app/consultas"
              element={<button onClick={() => void apiRequest('/api/v1/appointments').catch(() => undefined)}>Load</button>}
            />
            <Route path="/login" element={<LoginDestination />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    screen.getByRole('button', { name: 'Load' }).click()

    await waitFor(() => expect(screen.getByText('Login from /app/consultas?dia=hoje')).toBeInTheDocument())
    expect(queryClient.getQueryData(SESSION_QUERY_KEY)).toBeNull()
    expect(queryClient.getQueryData(['appointments'])).toBeUndefined()
  })

  it('does not turn an expected login 401 into global session loss', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    queryClient.setQueryData(SESSION_QUERY_KEY, {
      id: 'u1',
      email: 'ana@example.com',
      full_name: 'Ana',
      role: 'patient',
      clinic_id: 'c1',
    })
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ detail: 'Credenciais inválidas.' }),
      }),
    )

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/login']}>
          <AuthCoordinator />
          <Routes>
            <Route
              path="/login"
              element={<button onClick={() => void apiRequest('/api/v1/auth/login').catch(() => undefined)}>Login</button>}
            />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    screen.getByRole('button', { name: 'Login' }).click()
    await waitFor(() => expect(fetch).toHaveBeenCalled())
    expect(hasSession(queryClient)).toBe(true)
  })

  it('coordinates simultaneous 401 responses into one session-loss broadcast', async () => {
    vi.stubGlobal('BroadcastChannel', undefined)
    const broadcast = vi.spyOn(Storage.prototype, 'setItem')
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    queryClient.setQueryData(SESSION_QUERY_KEY, {
      id: 'u1',
      email: 'ana@example.com',
      full_name: 'Ana',
      role: 'patient',
      clinic_id: 'c1',
    })
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ detail: 'Sessão expirada.' }),
      }),
    )

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/app']}>
          <AuthCoordinator />
          <Routes>
            <Route
              path="/app"
              element={
                <button
                  onClick={() =>
                    void Promise.allSettled([
                      apiRequest('/api/v1/appointments'),
                      apiRequest('/api/v1/patients'),
                    ])
                  }
                >
                  Load twice
                </button>
              }
            />
            <Route path="/login" element={<LoginDestination />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    screen.getByRole('button', { name: 'Load twice' }).click()
    await waitFor(() => expect(queryClient.getQueryData(SESSION_QUERY_KEY)).toBeNull())
    expect(broadcast).toHaveBeenCalledTimes(1)
  })
})

function hasSession(queryClient: QueryClient) {
  return queryClient.getQueryData(SESSION_QUERY_KEY) !== null
}
