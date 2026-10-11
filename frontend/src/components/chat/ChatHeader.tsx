import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Avatar } from '../Avatar'
import { Icon } from '../Icon'

/**
 * Conversation header: back, the team member's initials and name, and a ⋮ menu
 * with the conversation state. Patients cannot change or close a conversation
 * (only the care team can), so the ⋮ menu only informs.
 */
export function ChatHeader({ backTo, name, subtitle, statusLabel, statusDescription }: {
  backTo: string
  name: string
  subtitle: string
  statusLabel: string
  statusDescription: string
}) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!open) return
    function onPointerDown(event: PointerEvent) {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false)
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== 'Escape') return
      setOpen(false)
      buttonRef.current?.focus()
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  return (
    <header className="sticky top-16 z-20 -mx-4 flex items-center gap-2 border-b border-slate-100 bg-white px-2 py-2 md:-mx-8 md:px-4">
      <Link
        to={backTo}
        aria-label="Voltar às mensagens"
        className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-slate-700 hover:bg-slate-100"
      >
        <Icon name="back" />
      </Link>
      <Avatar name={name} />
      <div className="min-w-0 flex-1">
        <h1 className="truncate text-lg font-semibold text-slate-900">{name}</h1>
        <p className="truncate text-sm text-slate-600">{subtitle}</p>
      </div>
      <div ref={containerRef} className="relative">
        <button
          ref={buttonRef}
          type="button"
          aria-label="Mais opções"
          aria-expanded={open}
          aria-controls="conversation-options"
          onClick={() => setOpen((value) => !value)}
          className="inline-flex h-11 w-11 items-center justify-center rounded-full text-slate-700 hover:bg-slate-100"
        >
          <Icon name="more" strokeWidth={3} />
        </button>
        {open && (
          <section
            id="conversation-options"
            aria-labelledby="conversation-state-heading"
            className="absolute right-0 z-30 mt-2 w-72 rounded-xl border border-slate-100 bg-white p-4 shadow-lg"
          >
            <h2 id="conversation-state-heading" className="text-base font-semibold text-slate-900">Estado da conversa</h2>
            <p className="mt-1 text-base font-medium text-teal-800">{statusLabel}</p>
            <p className="mt-1 text-sm text-slate-600">{statusDescription}</p>
          </section>
        )}
      </div>
    </header>
  )
}
