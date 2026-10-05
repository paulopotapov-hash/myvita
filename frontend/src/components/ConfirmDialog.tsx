import { useEffect, useRef, type ReactNode } from 'react'
import { Button } from './Button'

interface Props {
  title: string
  description: string
  confirmLabel: string
  isPending?: boolean
  onConfirm: () => void
  onCancel: () => void
  children?: ReactNode
}

export function ConfirmDialog({ title, description, confirmLabel, isPending = false, onConfirm, onCancel, children }: Props) {
  const cancelRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    cancelRef.current?.focus()
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape' && !isPending) onCancel()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isPending, onCancel])

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-950/50 p-4" onMouseDown={(event) => { if (event.target === event.currentTarget && !isPending) onCancel() }}>
      <section role="alertdialog" aria-modal="true" aria-labelledby="confirm-dialog-title" aria-describedby="confirm-dialog-description" className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
        <h2 id="confirm-dialog-title" className="text-lg font-semibold text-slate-900">{title}</h2>
        <p id="confirm-dialog-description" className="mt-2 text-sm text-slate-600">{description}</p>
        {children}
        <div className="mt-6 flex justify-end gap-3">
          <button ref={cancelRef} type="button" disabled={isPending} onClick={onCancel} className="inline-flex items-center justify-center rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 focus-visible:outline-2 disabled:opacity-60">Voltar</button>
          <Button isLoading={isPending} onClick={onConfirm}>{confirmLabel}</Button>
        </div>
      </section>
    </div>
  )
}
