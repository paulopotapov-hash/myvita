/** "Ana Maria Silva" -> "AS"; one name -> its first letter; empty -> "?". */
export function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  const first = parts[0][0] ?? ''
  const last = parts.length > 1 ? (parts[parts.length - 1][0] ?? '') : ''
  return (first + last).toUpperCase()
}

/** "Ana Maria Silva" -> "Ana" (the greeting uses the first name only). */
export function firstNameOf(name: string): string {
  return name.trim().split(/\s+/)[0] ?? ''
}
