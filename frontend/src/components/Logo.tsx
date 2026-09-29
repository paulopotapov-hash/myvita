import { useState } from 'react'

type LogoSize = 'splash' | 'header' | 'auth'

const SIZES: Record<LogoSize, string> = {
  splash: 'h-28',
  header: 'h-7',
  auth: 'h-8',
}

/** Renders the supplied, unchanged 1024×1024 JPEG logo from public/. */
export function Logo({ alt = '', className, size = 'header' }: { alt?: string; className?: string; size?: LogoSize }) {
  const [failed, setFailed] = useState(false)
  if (failed) return null

  return (
    <img
      src="/logo.jpg"
      alt={alt}
      className={`inline-block max-w-full ${SIZES[size]} ${className ?? ''}`}
      draggable={false}
      onError={() => setFailed(true)}
    />
  )
}
