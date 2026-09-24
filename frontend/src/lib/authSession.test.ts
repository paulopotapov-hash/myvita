import { QueryClient } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SESSION_QUERY_KEY } from '../hooks/useSession'
import {
  clearAuthenticatedState,
  hasAuthenticatedSession,
  publishAuthEvent,
  safeReturnTo,
  subscribeToAuthEvents,
} from './authSession'

describe('authSession', () => {
  it('clears user-scoped cache and leaves an explicit unauthenticated session', () => {
    const queryClient = new QueryClient()
    queryClient.setQueryData(SESSION_QUERY_KEY, { id: 'u1', role: 'patient' })
    queryClient.setQueryData(['patients'], [{ id: 'p1' }])

    clearAuthenticatedState(queryClient)

    expect(queryClient.getQueryData(SESSION_QUERY_KEY)).toBeNull()
    expect(queryClient.getQueryData(['patients'])).toBeUndefined()
    expect(hasAuthenticatedSession(queryClient)).toBe(false)
  })

  it('accepts only internal protected return destinations', () => {
    expect(safeReturnTo('/app/consultas?dia=hoje#lista')).toBe('/app/consultas?dia=hoje#lista')
    expect(safeReturnTo('https://evil.example')).toBe('/app')
    expect(safeReturnTo('//evil.example/app')).toBe('/app')
    expect(safeReturnTo('/login')).toBe('/app')
    expect(safeReturnTo('/application')).toBe('/app')
  })

  it('uses storage events as a cross-tab fallback without storing session data', () => {
    vi.stubGlobal('BroadcastChannel', undefined)
    const listener = vi.fn()
    const unsubscribe = subscribeToAuthEvents(listener)

    window.dispatchEvent(
      new StorageEvent('storage', {
        key: 'myvita-auth-event',
        newValue: JSON.stringify({ event: 'logout', at: Date.now() }),
      }),
    )

    expect(listener).toHaveBeenCalledWith('logout')
    unsubscribe()
  })

  it('broadcasts only an event marker and no authentication credentials', () => {
    vi.stubGlobal('BroadcastChannel', undefined)
    const setItem = vi.spyOn(Storage.prototype, 'setItem')

    publishAuthEvent('logout')

    expect(setItem).toHaveBeenCalledOnce()
    const payload = String(setItem.mock.calls[0][1])
    expect(payload).toContain('logout')
    expect(payload).not.toMatch(/jwt|cookie|csrf|password|token/i)
  })
})

afterEach(() => vi.unstubAllGlobals())
