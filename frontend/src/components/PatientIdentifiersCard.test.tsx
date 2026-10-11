import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../lib/apiClient'
import { PatientIdentifiersCard } from './PatientIdentifiersCard'

// Synthetic identifiers only.
const FULL = { nif: '123456789', niss: '12345678902', national_health_number: '987654321' }
const MASKED = { nif: '••••••789', niss: '••••••••902', national_health_number: '••••••321' }

const h = vi.hoisted(() => ({
  canEdit: true,
  reveal: vi.fn(),
  update: vi.fn(),
}))

vi.mock('../hooks/useClinicData', () => ({
  usePatientIdentification: () => ({
    data: { id: 'p1', full_name: 'Ana Silva', identifiers: MASKED, can_edit: h.canEdit },
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
  useRevealIdentifiers: () => ({ mutate: h.reveal, isPending: false }),
  useUpdateIdentifiers: () => ({ mutate: h.update, isPending: false }),
}))

type Callbacks<T> = { onSuccess?: (value: T) => void; onError?: (error: unknown) => void }

beforeEach(() => {
  h.canEdit = true
  h.reveal.mockReset()
  h.update.mockReset()
  h.reveal.mockImplementation((_: unknown, callbacks: Callbacks<typeof FULL>) => callbacks.onSuccess?.(FULL))
})

function card() {
  return screen.getByRole('region', { name: 'Dados identificativos' })
}

describe('PatientIdentifiersCard', () => {
  it('shows only the masked values until "Mostrar", which calls the audited reveal endpoint', async () => {
    const user = userEvent.setup()
    render(<PatientIdentifiersCard patientId="p1" />)
    expect(card()).toHaveTextContent('••••••789')
    expect(card()).not.toHaveTextContent('123456789')
    expect(h.reveal).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: 'Mostrar dados identificativos' }))
    expect(h.reveal).toHaveBeenCalledTimes(1)
    expect(card()).toHaveTextContent('123456789')
    expect(card()).toHaveTextContent('12345678902')

    await user.click(screen.getByRole('button', { name: 'Ocultar dados identificativos' }))
    expect(card()).not.toHaveTextContent('123456789')
  })

  it('offers no editing when the backend says the user may not change them (the patient)', () => {
    h.canEdit = false
    render(<PatientIdentifiersCard patientId="p1" />)
    expect(screen.getByRole('button', { name: 'Mostrar dados identificativos' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Editar/ })).not.toBeInTheDocument()
  })

  it('validates check digits before sending and then sends only the fields that changed', async () => {
    const user = userEvent.setup()
    render(<PatientIdentifiersCard patientId="p1" />)
    await user.click(screen.getByRole('button', { name: 'Editar dados identificativos' }))
    const form = screen.getByRole('form', { name: 'Editar dados identificativos' })
    expect(within(form).getByLabelText('NIF')).toHaveValue('123456789')

    await user.clear(within(form).getByLabelText('NIF'))
    await user.type(within(form).getByLabelText('NIF'), '123456788')
    await user.click(within(form).getByRole('button', { name: 'Guardar' }))
    expect(within(form).getByText('NIF inválido: confirma os 9 dígitos.')).toBeInTheDocument()
    expect(within(form).getByLabelText('NIF')).toHaveFocus()
    expect(h.update).not.toHaveBeenCalled()

    await user.clear(within(form).getByLabelText('NIF'))
    await user.type(within(form).getByLabelText('NIF'), '234 567 899')
    await user.clear(within(form).getByLabelText('NISS'))
    await user.click(within(form).getByRole('button', { name: 'Guardar' }))
    expect(h.update).toHaveBeenCalledWith({ nif: '234567899', niss: null }, expect.any(Object))

    const callbacks = h.update.mock.calls[0][1] as Callbacks<unknown>
    act(() => callbacks.onSuccess?.({}))
    expect(screen.getByRole('status')).toHaveTextContent('Dados identificativos atualizados.')
    // Back to the masked view after saving.
    expect(card()).not.toHaveTextContent('123456789')
  })

  it('shows the backend message for a NIF already used in the clinic', async () => {
    const user = userEvent.setup()
    render(<PatientIdentifiersCard patientId="p1" />)
    await user.click(screen.getByRole('button', { name: 'Editar dados identificativos' }))
    const form = screen.getByRole('form', { name: 'Editar dados identificativos' })
    await user.clear(within(form).getByLabelText('NIF'))
    await user.type(within(form).getByLabelText('NIF'), '234567899')
    await user.click(within(form).getByRole('button', { name: 'Guardar' }))
    const callbacks = h.update.mock.calls[0][1] as Callbacks<unknown>
    act(() => callbacks.onError?.(new ApiError(409, 'conflict', { detail: 'Já existe um paciente nesta clínica com este NIF.' })))
    expect(within(form).getByRole('alert')).toHaveTextContent('Já existe um paciente nesta clínica com este NIF.')
  })
})
