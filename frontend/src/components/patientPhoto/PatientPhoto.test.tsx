import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Avatar } from '../Avatar'
import { PhotoReviewCard } from './PhotoReviewCard'
import { ProfilePhotoSection } from './ProfilePhotoSection'

const h = vi.hoisted(() => ({
  mine: null as unknown,
  upload: vi.fn(),
  remove: vi.fn(),
  decide: vi.fn(),
}))

vi.mock('../../hooks/usePatientPhoto', () => ({
  useMyPhoto: () => ({ data: h.mine, isLoading: false, isError: false }),
  useUploadPhoto: () => ({ mutate: h.upload, isPending: false }),
  useRemovePhoto: () => ({ mutate: h.remove, isPending: false }),
  usePhotoDecision: () => ({ mutate: h.decide, isPending: false }),
}))

const REQUIREMENTS = ['A cores.', 'Com o rosto bem visível.', 'Sem filtros nem efeitos.', 'Só tu na fotografia.']

beforeEach(() => {
  h.mine = { approved: null, pending: null, rejected: null, requirements: REQUIREMENTS }
  h.upload.mockReset()
  h.remove.mockReset()
  h.decide.mockReset()
})

describe('Foto de perfil (paciente)', () => {
  it('shows the requirements and both ways to add a photo', () => {
    render(<ProfilePhotoSection name="Ana Silva" />)
    const section = screen.getByRole('region', { name: 'Foto de perfil' })
    for (const item of REQUIREMENTS) expect(within(section).getByText(item)).toBeInTheDocument()
    expect(within(section).getByRole('button', { name: 'Tirar foto' })).toBeInTheDocument()
    expect(within(section).getByRole('button', { name: 'Escolher da galeria' })).toBeInTheDocument()
    expect(screen.getByTestId('photo-camera-input')).toHaveAttribute('capture', 'user')
    expect(screen.getByTestId('photo-gallery-input')).toHaveAttribute('accept', 'image/jpeg,image/png')
    expect(within(section).getByText('Sem foto aprovada')).toBeInTheDocument()
  })

  it('shows a pending photo as such, next to the approved one still in use', () => {
    h.mine = { approved: { id: 'ap', created_at: '2026-10-01T10:00:00Z' }, pending: { id: 'pe', created_at: '2026-10-12T10:00:00Z' }, rejected: null, requirements: REQUIREMENTS }
    const { container } = render(<ProfilePhotoSection name="Ana Silva" />)
    expect(screen.getByText('Pendente de aprovação')).toBeInTheDocument()
    expect([...container.querySelectorAll('img')].map((img) => img.getAttribute('src'))).toEqual([
      '/api/v1/patient-photos/ap/image',
      '/api/v1/patient-photos/pe/image',
    ])
  })

  it('shows the doctor\'s reason after a rejection', () => {
    h.mine = { approved: null, pending: null, rejected: { reason: 'O rosto não está visível.', rejected_at: null }, requirements: REQUIREMENTS }
    render(<ProfilePhotoSection name="Ana Silva" />)
    expect(screen.getByText('A tua última foto não foi aprovada: O rosto não está visível.')).toBeInTheDocument()
  })

  it('refuses other formats and files over 5 MB before sending anything', () => {
    render(<ProfilePhotoSection name="Ana Silva" />)
    const input = screen.getByTestId('photo-gallery-input')
    fireEvent.change(input, { target: { files: [new File(['GIF89a'], 'a.gif', { type: 'image/gif' })] } })
    expect(screen.getByText('Escolhe uma fotografia em JPEG ou PNG.')).toBeInTheDocument()
    const big = new File([new Uint8Array(5 * 1024 * 1024 + 1)], 'big.jpg', { type: 'image/jpeg' })
    fireEvent.change(input, { target: { files: [big] } })
    expect(screen.getByText('A foto não pode ter mais de 5 MB.')).toBeInTheDocument()
    expect(h.upload).not.toHaveBeenCalled()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('removes a photo only after confirming', async () => {
    h.mine = { approved: { id: 'ap', created_at: '2026-10-01T10:00:00Z' }, pending: null, rejected: null, requirements: REQUIREMENTS }
    const user = userEvent.setup()
    render(<ProfilePhotoSection name="Ana Silva" />)
    await user.click(screen.getByRole('button', { name: 'Remover foto' }))
    const dialog = screen.getByRole('alertdialog', { name: 'Remover a foto?' })
    expect(dialog).toHaveTextContent('apagada de imediato e de forma definitiva')
    await user.click(within(dialog).getByRole('button', { name: 'Remover' }))
    expect(h.remove).toHaveBeenCalledWith('ap', expect.any(Object))
  })
})

describe('Foto de perfil por aprovar (médico)', () => {
  it('approves, or rejects with a reason the patient will read', async () => {
    const user = userEvent.setup()
    render(<PhotoReviewCard name="Ana Silva" pending={{ id: 'pe', created_at: '2026-10-12T10:00:00Z' }} />)
    const card = screen.getByRole('region', { name: 'Foto de perfil por aprovar' })
    expect(card.querySelector('img')).toHaveAttribute('src', '/api/v1/patient-photos/pe/image')
    await user.click(within(card).getByRole('button', { name: 'Aprovar' }))
    expect(h.decide).toHaveBeenLastCalledWith({ photoId: 'pe', approve: true }, expect.any(Object))

    await user.click(within(card).getByRole('button', { name: 'Rejeitar…' }))
    await user.click(within(card).getByRole('button', { name: 'Rejeitar foto' }))
    expect(within(card).getByText('Indica o motivo, que o paciente vai ler.')).toBeInTheDocument()
    await user.type(within(card).getByLabelText('Motivo da rejeição (o paciente vai ler)'), 'Rosto tapado.')
    await user.click(within(card).getByRole('button', { name: 'Rejeitar foto' }))
    expect(h.decide).toHaveBeenLastCalledWith({ photoId: 'pe', approve: false, reason: 'Rosto tapado.' }, expect.any(Object))
  })
})

describe('Avatar', () => {
  it('shows the photo when given one, and the initials otherwise or if it fails to load', () => {
    const { container, rerender } = render(<Avatar name="Ana Silva" photoUrl="/api/v1/patient-photos/ap/image" />)
    const img = container.querySelector('img')!
    expect(img).toHaveAttribute('alt', '')
    fireEvent.error(img)
    expect(container.querySelector('img')).toBeNull()
    expect(container).toHaveTextContent('AS')
    rerender(<Avatar name="Ana Silva" />)
    expect(container).toHaveTextContent('AS')
  })
})
