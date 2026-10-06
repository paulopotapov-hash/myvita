import { act, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../lib/apiClient'
import type { MedicationPublic } from '../../types/api'
import { MedicationsSection } from './MedicationsSection'

const h = vi.hoisted(() => ({
  list: { data: undefined as unknown, isLoading: false, isError: false, error: null as unknown, refetch: vi.fn() },
  create: { mutate: vi.fn(), isPending: false },
  update: { mutate: vi.fn(), isPending: false, variables: undefined as unknown },
  deactivate: { mutate: vi.fn(), isPending: false, variables: undefined as unknown },
}))

vi.mock('../../hooks/useClinicalData', () => ({
  useMedications: () => h.list,
  useCreateMedication: () => h.create,
  useUpdateMedication: () => h.update,
  useDeactivateMedication: () => h.deactivate,
}))

const active: MedicationPublic = {
  id: 'med-1',
  clinic_id: 'clinic-1',
  patient_id: 'patient-1',
  prescribed_by_staff_id: 'staff-1',
  name: 'Amoxicilina',
  dosage: '500 mg',
  route: 'oral',
  frequency: '8/8h',
  instructions: 'Após as refeições',
  status: 'active',
  start_date: '2026-09-24',
  end_date: null,
  created_at: '2026-09-24T10:00:00Z',
  updated_at: '2026-09-24T10:00:00Z',
}
const completed: MedicationPublic = { ...active, id: 'med-2', name: 'Ibuprofeno', status: 'completed', end_date: '2026-09-30', route: null, frequency: null, instructions: null }

function setItems(items: MedicationPublic[], total = items.length) {
  h.list.data = { items, total }
}

function renderSection(canWrite = true) {
  return render(<MedicationsSection patientId="patient-1" canWrite={canWrite} />)
}

async function fillCreateForm(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText('Medicamento'), 'Paracetamol')
  await user.type(screen.getByLabelText('Dosagem'), '1 g')
  fireEvent.change(screen.getByLabelText('Data de início'), { target: { value: '2026-10-01' } })
}

describe('MedicationsSection', () => {
  beforeEach(() => {
    h.list = { data: undefined, isLoading: false, isError: false, error: null, refetch: vi.fn() }
    h.create = { mutate: vi.fn(), isPending: false }
    h.update = { mutate: vi.fn(), isPending: false, variables: undefined }
    h.deactivate = { mutate: vi.fn(), isPending: false, variables: undefined }
    vi.spyOn(window, 'confirm').mockReturnValue(true)
  })

  describe('states and display', () => {
    it('shows a loading state', () => {
      h.list.isLoading = true
      renderSection()
      expect(screen.getByRole('status')).toHaveTextContent('A carregar')
    })

    it('shows a retryable error state', async () => {
      h.list.isError = true
      h.list.error = new ApiError(503, 'x')
      const user = userEvent.setup()
      renderSection()
      expect(screen.getByRole('alert')).toHaveTextContent('temporariamente indisponível')
      await user.click(screen.getByRole('button', { name: 'Tentar novamente' }))
      expect(h.list.refetch).toHaveBeenCalled()
    })

    it('shows an empty state that points writers to the form', () => {
      setItems([])
      renderSection()
      expect(screen.getByText('Sem medicação')).toBeInTheDocument()
      expect(screen.getByText(/formulário acima/)).toBeInTheDocument()
    })

    it('shows the full medication: status, dates, route, frequency and instructions', () => {
      setItems([{ ...active, end_date: '2026-10-10' }, completed])
      renderSection()
      expect(screen.getByText('Amoxicilina · 500 mg')).toBeInTheDocument()
      expect(screen.getByText('Ativa')).toBeInTheDocument()
      expect(screen.getByText('Concluída')).toBeInTheDocument()
      expect(screen.getByText(/Via oral/)).toBeInTheDocument()
      expect(screen.getByText(/8\/8h/)).toBeInTheDocument()
      expect(screen.getAllByText(/· Fim/)).toHaveLength(2)
      expect(screen.getByText('Após as refeições')).toBeInTheDocument()
    })

    it('warns when the server holds more medications than are displayed', () => {
      setItems([active], 120)
      renderSection()
      expect(screen.getByText(/1 medicações mais recentes de 120/)).toBeInTheDocument()
    })

    it('is read-only without write permission', () => {
      setItems([active])
      renderSection(false)
      expect(screen.queryByLabelText('Medicamento')).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Adicionar medicação' })).not.toBeInTheDocument()
      for (const name of ['Editar', 'Concluir', 'Descontinuar']) {
        expect(screen.queryByRole('button', { name })).not.toBeInTheDocument()
      }
      expect(screen.getByText('Amoxicilina · 500 mg')).toBeInTheDocument()
    })

    it('offers actions only on active medications', () => {
      setItems([completed])
      renderSection()
      expect(screen.queryByRole('button', { name: 'Editar' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Concluir' })).not.toBeInTheDocument()
    })
  })

  describe('create', () => {
    it('blocks an empty submit with field-level messages and no request', async () => {
      const user = userEvent.setup()
      renderSection()
      await user.click(screen.getByRole('button', { name: 'Adicionar medicação' }))
      expect(screen.getByText('Indica o nome do medicamento.')).toBeInTheDocument()
      expect(screen.getByText('Indica a dosagem.')).toBeInTheDocument()
      expect(screen.getByText('Indica a data de início.')).toBeInTheDocument()
      expect(screen.getByLabelText('Medicamento')).toHaveAttribute('aria-invalid', 'true')
      expect(h.create.mutate).not.toHaveBeenCalled()
    })

    it('blocks an end date before the start date', async () => {
      const user = userEvent.setup()
      renderSection()
      await fillCreateForm(user)
      fireEvent.change(screen.getByLabelText('Data de fim (opcional)'), { target: { value: '2026-09-01' } })
      await user.click(screen.getByRole('button', { name: 'Adicionar medicação' }))
      expect(screen.getByText('A data de fim não pode ser anterior à data de início.')).toBeInTheDocument()
      expect(h.create.mutate).not.toHaveBeenCalled()
    })

    it('sends the complete backend contract, omitting empty optional fields', async () => {
      const user = userEvent.setup()
      renderSection()
      await fillCreateForm(user)
      await user.click(screen.getByRole('button', { name: 'Adicionar medicação' }))
      expect(h.create.mutate).toHaveBeenCalledWith(
        { name: 'Paracetamol', dosage: '1 g', start_date: '2026-10-01' },
        expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
      )

      await user.type(screen.getByLabelText('Via de administração (opcional)'), 'oral')
      await user.type(screen.getByLabelText('Frequência (opcional)'), '6/6h')
      await user.type(screen.getByLabelText('Instruções (opcional)'), 'Com água')
      fireEvent.change(screen.getByLabelText('Data de fim (opcional)'), { target: { value: '2026-10-10' } })
      await user.click(screen.getByRole('button', { name: 'Adicionar medicação' }))
      expect(h.create.mutate).toHaveBeenLastCalledWith(
        {
          name: 'Paracetamol',
          dosage: '1 g',
          route: 'oral',
          frequency: '6/6h',
          instructions: 'Com água',
          start_date: '2026-10-01',
          end_date: '2026-10-10',
        },
        expect.anything(),
      )
    })

    it('confirms success and clears the form', async () => {
      const user = userEvent.setup()
      renderSection()
      await fillCreateForm(user)
      await user.click(screen.getByRole('button', { name: 'Adicionar medicação' }))
      const options = h.create.mutate.mock.calls.at(-1)?.[1] as { onSuccess: () => void }
      act(() => options.onSuccess())
      expect(await screen.findByRole('status')).toHaveTextContent('Medicação adicionada.')
      expect(screen.getByLabelText('Medicamento')).toHaveValue('')
    })

    it('shows backend field errors next to the field and root errors as an alert', async () => {
      const user = userEvent.setup()
      renderSection()
      await fillCreateForm(user)
      await user.click(screen.getByRole('button', { name: 'Adicionar medicação' }))
      const options = h.create.mutate.mock.calls.at(-1)?.[1] as { onError: (error: unknown) => void }

      act(() => options.onError(new ApiError(422, 'x', { fieldErrors: { dosage: 'Valor inválido' } })))
      expect(await screen.findByText('Valor inválido')).toBeInTheDocument()
      expect(screen.getByLabelText('Dosagem')).toHaveAttribute('aria-invalid', 'true')

      act(() => options.onError(new ApiError(403, 'x', { detail: 'Sem permissões clínicas.' })))
      expect(await screen.findByRole('alert')).toHaveTextContent('Sem permissões clínicas.')
    })

    it('prevents double submit and shows the pending state', () => {
      h.create.isPending = true
      renderSection()
      const button = screen.getByRole('button', { name: 'Adicionar medicação' })
      expect(button).toBeDisabled()
      expect(button).toHaveAttribute('aria-busy', 'true')
    })
  })

  describe('edit', () => {
    it('pre-fills the form and sends only the changed fields', async () => {
      setItems([active])
      const user = userEvent.setup()
      renderSection()
      await user.click(screen.getByRole('button', { name: 'Editar' }))
      expect(screen.getByLabelText('Medicamento')).toHaveValue('Amoxicilina')
      expect(screen.getByLabelText('Instruções (opcional)')).toHaveValue('Após as refeições')

      await user.clear(screen.getByLabelText('Dosagem'))
      await user.type(screen.getByLabelText('Dosagem'), '250 mg')
      await user.clear(screen.getByLabelText('Instruções (opcional)'))
      await user.click(screen.getByRole('button', { name: 'Guardar alterações' }))
      expect(h.update.mutate).toHaveBeenCalledWith(
        { id: 'med-1', payload: { dosage: '250 mg', instructions: null } },
        expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
      )
    })

    it('does not call the API when nothing changed', async () => {
      setItems([active])
      const user = userEvent.setup()
      renderSection()
      await user.click(screen.getByRole('button', { name: 'Editar' }))
      await user.click(screen.getByRole('button', { name: 'Guardar alterações' }))
      expect(screen.getByRole('alert')).toHaveTextContent('Não há alterações para guardar.')
      expect(h.update.mutate).not.toHaveBeenCalled()
    })

    it('validates edits and can be cancelled', async () => {
      setItems([active])
      const user = userEvent.setup()
      renderSection()
      await user.click(screen.getByRole('button', { name: 'Editar' }))
      await user.clear(screen.getByLabelText('Dosagem'))
      await user.click(screen.getByRole('button', { name: 'Guardar alterações' }))
      expect(screen.getByText('Indica a dosagem.')).toBeInTheDocument()
      expect(h.update.mutate).not.toHaveBeenCalled()

      await user.click(screen.getByRole('button', { name: 'Cancelar edição' }))
      expect(screen.getByLabelText('Dosagem')).toHaveValue('')
      expect(screen.getByRole('button', { name: 'Adicionar medicação' })).toBeInTheDocument()
    })

    it('confirms a successful edit', async () => {
      setItems([active])
      const user = userEvent.setup()
      renderSection()
      await user.click(screen.getByRole('button', { name: 'Editar' }))
      await user.type(screen.getByLabelText('Frequência (opcional)'), ' SOS')
      await user.click(screen.getByRole('button', { name: 'Guardar alterações' }))
      const options = h.update.mutate.mock.calls.at(-1)?.[1] as { onSuccess: () => void }
      act(() => options.onSuccess())
      expect(await screen.findByRole('status')).toHaveTextContent('Medicação atualizada.')
      expect(screen.getByRole('button', { name: 'Adicionar medicação' })).toBeInTheDocument()
    })
  })

  describe('termination (destructive, needs confirmation)', () => {
    it('does nothing when the confirmation is declined', async () => {
      vi.spyOn(window, 'confirm').mockReturnValue(false)
      setItems([active])
      const user = userEvent.setup()
      renderSection()
      await user.click(screen.getByRole('button', { name: 'Concluir' }))
      await user.click(screen.getByRole('button', { name: 'Descontinuar' }))
      expect(window.confirm).toHaveBeenCalledTimes(2)
      expect(h.update.mutate).not.toHaveBeenCalled()
      expect(h.deactivate.mutate).not.toHaveBeenCalled()
    })

    it('completes a medication through the status update', async () => {
      setItems([active])
      const user = userEvent.setup()
      renderSection()
      await user.click(screen.getByRole('button', { name: 'Concluir' }))
      expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('Amoxicilina'))
      expect(h.update.mutate).toHaveBeenCalledWith(
        { id: 'med-1', payload: { status: 'completed' } },
        expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
      )
      const options = h.update.mutate.mock.calls.at(-1)?.[1] as { onSuccess: () => void }
      act(() => options.onSuccess())
      expect(await screen.findByRole('status')).toHaveTextContent('Medicação concluída.')
    })

    it('discontinues a medication through the dedicated endpoint', async () => {
      setItems([active])
      const user = userEvent.setup()
      renderSection()
      await user.click(screen.getByRole('button', { name: 'Descontinuar' }))
      expect(h.deactivate.mutate).toHaveBeenCalledWith(
        'med-1',
        expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
      )
      const options = h.deactivate.mutate.mock.calls.at(-1)?.[1] as { onSuccess: () => void; onError: (e: unknown) => void }
      act(() => options.onSuccess())
      expect(await screen.findByRole('status')).toHaveTextContent('Medicação descontinuada.')
      act(() => options.onError(new ApiError(409, 'x', { detail: 'Medicação já terminada.' })))
      expect(await screen.findByRole('alert')).toHaveTextContent('Medicação já terminada.')
    })

    it('locks every action while a request runs and spins only the running one', () => {
      setItems([active])
      h.deactivate.isPending = true
      h.deactivate.variables = 'med-1'
      renderSection()
      const row = screen.getByRole('listitem')
      expect(within(row).getByRole('button', { name: 'Editar' })).toBeDisabled()
      expect(within(row).getByRole('button', { name: 'Concluir' })).toBeDisabled()
      expect(within(row).getByRole('button', { name: 'Descontinuar' })).toHaveAttribute('aria-busy', 'true')
      expect(within(row).getByRole('button', { name: 'Concluir' })).toHaveAttribute('aria-busy', 'false')
      expect(screen.getByRole('button', { name: 'Adicionar medicação' })).toBeDisabled()
    })
  })

  it('moves focus to the first invalid field after a failed submit', async () => {
    const user = userEvent.setup()
    renderSection()
    await user.click(screen.getByRole('button', { name: 'Adicionar medicação' }))
    expect(screen.getByLabelText('Medicamento')).toHaveFocus()
    expect(screen.getByLabelText('Medicamento')).toBeRequired()
    expect(screen.getByLabelText('Medicamento')).toHaveAccessibleDescription('Indica o nome do medicamento.')
  })

  it('gives each row action the medication it acts on as its description', () => {
    setItems([active])
    renderSection()
    for (const name of ['Editar', 'Concluir', 'Descontinuar']) {
      expect(screen.getByRole('button', { name })).toHaveAccessibleDescription('Amoxicilina · 500 mg')
    }
  })
})
