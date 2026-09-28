import type { UserRole } from '../types/api'

export function homePathForRole(role: UserRole): '/patient' | '/app' {
  return role === 'patient' ? '/patient' : '/app'
}

export function safePostLoginPath(state: unknown, role: UserRole): string {
  const homePath = homePathForRole(role)
  if (typeof state !== 'object' || state === null || !('from' in state)) return homePath
  const from = (state as { from?: unknown }).from
  if (typeof from !== 'string') return homePath

  // Router state is untrusted: only the current role's area is restorable,
  // and protocol-relative URLs, backslashes or control characters are rejected.
  const hasUnsafeCharacter = [...from].some((character) => {
    const code = character.charCodeAt(0)
    return character === '\\' || code <= 31 || code === 127
  })
  const roleAreaPattern = role === 'patient' ? /^\/patient(?:[/?#]|$)/ : /^\/app(?:[/?#]|$)/
  if (!roleAreaPattern.test(from) || hasUnsafeCharacter) return homePath
  return from
}
