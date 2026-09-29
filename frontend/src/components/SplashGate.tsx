import { useEffect, useState, type ReactNode } from 'react'
import { Logo } from './Logo'

export const SPLASH_VISIBLE_MS = 1200
export const SPLASH_FADE_MS = 400

type SplashPhase = 'visible' | 'fading' | 'done'

function initialPhase(): SplashPhase {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'done' : 'visible'
}

/** Brief splash overlay; the current route is rendered after the fade starts. */
export function SplashGate({ children }: { children: ReactNode }) {
  const [phase, setPhase] = useState<SplashPhase>(initialPhase)

  useEffect(() => {
    if (phase === 'done') return
    const delay = phase === 'visible' ? SPLASH_VISIBLE_MS : SPLASH_FADE_MS
    const timer = window.setTimeout(() => setPhase(phase === 'visible' ? 'fading' : 'done'), delay)
    return () => window.clearTimeout(timer)
  }, [phase])

  if (phase === 'done') return <>{children}</>

  return (
    <>
      {phase === 'fading' && children}
      <div
        aria-hidden="true"
        className={`fixed inset-0 z-50 flex items-center justify-center bg-slate-50 ${
          phase === 'fading' ? 'pointer-events-none opacity-0 transition-opacity duration-[400ms] ease-out' : ''
        }`}
      >
        <Logo alt="myVita" size="splash" />
      </div>
    </>
  )
}
