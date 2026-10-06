import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { Modal } from './Modal'

function Harness({ onClose = () => {} }: { onClose?: () => void }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>Abrir</button>
      {open && (
        <Modal titleId="t" onClose={() => { onClose(); setOpen(false) }}>
          <h2 id="t">Detalhe</h2>
          <input aria-label="Primeiro" />
          <button type="button">Último</button>
        </Modal>
      )}
    </>
  )
}

describe('Modal', () => {
  it('is a labelled modal dialog and moves focus into it', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.click(screen.getByRole('button', { name: 'Abrir' }))
    const dialog = screen.getByRole('dialog', { name: 'Detalhe' })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(dialog).toHaveFocus()
  })

  it('keeps Tab and Shift+Tab inside the dialog', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.click(screen.getByRole('button', { name: 'Abrir' }))
    await user.tab()
    expect(screen.getByLabelText('Primeiro')).toHaveFocus()
    await user.tab()
    expect(screen.getByRole('button', { name: 'Último' })).toHaveFocus()
    await user.tab()
    expect(screen.getByLabelText('Primeiro')).toHaveFocus()
    await user.tab({ shift: true })
    expect(screen.getByRole('button', { name: 'Último' })).toHaveFocus()
  })

  it('closes on Escape, restores focus to the opener and unlocks page scroll', async () => {
    const onClose = vi.fn()
    const user = userEvent.setup()
    render(<Harness onClose={onClose} />)
    const opener = screen.getByRole('button', { name: 'Abrir' })
    await user.click(opener)
    expect(document.body.style.overflow).toBe('hidden')
    await user.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledOnce()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(opener).toHaveFocus()
    expect(document.body.style.overflow).toBe('')
  })
})
