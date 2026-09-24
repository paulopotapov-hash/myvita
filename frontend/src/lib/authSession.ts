import type { QueryClient } from '@tanstack/react-query'
import { SESSION_QUERY_KEY } from '../hooks/useSession'
import type { UserPublic } from '../types/api'

export type AuthSyncEvent = 'login' | 'logout'

const CHANNEL_NAME = 'myvita-auth'
const STORAGE_KEY = 'myvita-auth-event'

let channel: BroadcastChannel | null = null

function getChannel(): BroadcastChannel | null {
  if (typeof window === 'undefined' || typeof window.BroadcastChannel !== 'function') return null
  channel ??= new BroadcastChannel(CHANNEL_NAME)
  return channel
}

/** Removes all user-scoped data and leaves an explicit unauthenticated
 * session value behind. `null` is intentional and is never interpreted as
 * an authenticated query result by useSession. */
export function clearAuthenticatedState(queryClient: QueryClient) {
  const isAuthenticatedQuery = (query: { queryKey: readonly unknown[] }) => query.queryKey[0] !== 'clinics'
  void queryClient.cancelQueries({ predicate: isAuthenticatedQuery })
  queryClient.removeQueries({ predicate: isAuthenticatedQuery })
  queryClient.getMutationCache().clear()
  queryClient.setQueryData(SESSION_QUERY_KEY, null)
}

export function hasAuthenticatedSession(queryClient: QueryClient): boolean {
  return Boolean(queryClient.getQueryData<UserPublic | null>(SESSION_QUERY_KEY))
}

/** Only protected application locations are valid post-login destinations.
 * This rejects absolute and protocol-relative URLs as well as public routes. */
export function safeReturnTo(value: unknown): string {
  if (typeof value !== 'string' || !value.startsWith('/app')) return '/app'
  if (value.startsWith('//') || value.includes('\\')) return '/app'
  try {
    const url = new URL(value, window.location.origin)
    const isProtectedPath = url.pathname === '/app' || url.pathname.startsWith('/app/')
    return url.origin === window.location.origin && isProtectedPath
      ? `${url.pathname}${url.search}${url.hash}`
      : '/app'
  } catch {
    return '/app'
  }
}

export function publishAuthEvent(event: AuthSyncEvent) {
  const broadcastChannel = getChannel()
  if (broadcastChannel) {
    broadcastChannel.postMessage(event)
    return
  }

  // Fallback for browsers without BroadcastChannel. This stores only a
  // short-lived event marker — never a token or authentication state.
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ event, at: Date.now() }))
    localStorage.removeItem(STORAGE_KEY)
  } catch {
    // Cross-tab sync is best-effort when browser storage is unavailable.
  }
}

export function subscribeToAuthEvents(listener: (event: AuthSyncEvent) => void): () => void {
  const broadcastChannel = getChannel()
  if (broadcastChannel) {
    const onMessage = (message: MessageEvent<AuthSyncEvent>) => listener(message.data)
    broadcastChannel.addEventListener('message', onMessage)
    return () => broadcastChannel.removeEventListener('message', onMessage)
  }

  const onStorage = (storageEvent: StorageEvent) => {
    if (storageEvent.key !== STORAGE_KEY || !storageEvent.newValue) return
    try {
      const parsed = JSON.parse(storageEvent.newValue) as { event?: AuthSyncEvent }
      if (parsed.event === 'login' || parsed.event === 'logout') listener(parsed.event)
    } catch {
      // Ignore malformed events from unrelated/manual storage writes.
    }
  }
  window.addEventListener('storage', onStorage)
  return () => window.removeEventListener('storage', onStorage)
}
