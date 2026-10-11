import { useState } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ConfirmDialog } from './ConfirmDialog'

function WithField({ onConfirm }: { onConfirm: (value: string) => void }) {
  const [value, setValue] = useState('')
  // The parent re-renders on every keystroke, with new callbacks each time.
  return (
    <ConfirmDialog title="Confirmar" description="D" confirmLabel="OK" onCancel={() => undefined} onConfirm={() => onConfirm(value)}>
      <label>Campo<input value={value} onChange={(event) => setValue(event.target.value)} /></label>
    </ConfirmDialog>
  )
}

describe('ConfirmDialog', () => {
  it('focuses the safe choice when it opens and never steals focus from a field inside it', async () => {
    const onConfirm = vi.fn()
    const user = userEvent.setup()
    render(<WithField onConfirm={onConfirm} />)
    expect(screen.getByRole('button', { name: 'Voltar' })).toHaveFocus()
    await user.type(screen.getByLabelText('Campo'), '1000 UI')
    expect(screen.getByLabelText('Campo')).toHaveFocus()
    await user.click(screen.getByRole('button', { name: 'OK' }))
    expect(onConfirm).toHaveBeenCalledWith('1000 UI')
  })
})
