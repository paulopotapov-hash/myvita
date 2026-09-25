export function safePostLoginPath(state: unknown): string {
  if (typeof state !== 'object' || state === null || !('from' in state)) return '/app'
  const from = (state as { from?: unknown }).from
  if (typeof from !== 'string') return '/app'

  // ProtectedRoute only creates destinations below /app. Treat route state
  // as untrusted nevertheless: protocol-relative URLs, backslashes and
  // control characters must never become post-login navigation targets.
  const hasUnsafeCharacter = [...from].some((character) => {
    const code = character.charCodeAt(0)
    return character === '\\' || code <= 31 || code === 127
  })
  if (!/^\/app(?:[/?#]|$)/.test(from) || hasUnsafeCharacter) return '/app'
  return from
}
