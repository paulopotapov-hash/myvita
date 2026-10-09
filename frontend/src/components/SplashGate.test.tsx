import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SPLASH_FADE_MS, SPLASH_VISIBLE_MS, SplashGate } from './SplashGate'

describe('SplashGate', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('shows a centered logo before revealing its child after 1.6 seconds', () => {
    render(<SplashGate><p>Conteúdo real</p></SplashGate>)

    expect(screen.queryByText('Conteúdo real')).not.toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'myVita', hidden: true })).toBeInTheDocument()

    act(() => vi.advanceTimersByTime(SPLASH_VISIBLE_MS))
    expect(screen.getByText('Conteúdo real')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'myVita', hidden: true })).toBeInTheDocument()

    act(() => vi.advanceTimersByTime(SPLASH_FADE_MS))
    expect(screen.queryByRole('img', { name: 'myVita', hidden: true })).not.toBeInTheDocument()
  })

  it('skips the splash for users who prefer reduced motion', () => {
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: true }))
    render(<SplashGate><p>Conteúdo real</p></SplashGate>)

    expect(screen.getByText('Conteúdo real')).toBeInTheDocument()
    expect(screen.queryByRole('img', { name: 'myVita', hidden: true })).not.toBeInTheDocument()
  })
})
