import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../lib/apiClient'
import type { ClinicalHistoryEntry } from '../../types/api'
import { ClinicalHistorySection } from './ClinicalHistorySection'

const h = vi.hoisted(() => ({ entries: [] as unknown[], mutate: vi.fn() }))

vi.mock('../../hooks/useClinicalHistory', () => ({
  useClinicalHistory: () => ({ data: h.entries, isLoading: false, isError: false, refetch: vi.fn() }),
  useClinicalHistoryAction: () => ({ mutate: h.mutate, isPending: false }),
}))

const base = {
  name: null, condition_status: null, onset: null, resolved: null, occurred: null, location: null, reaction: null,
  severity: null, note_text: null, confirmed_at: null, confirmed_by_name: null, created_at: '2026-10-01T10:00:00Z',
  updated_at: '2026-10-01T10:00:00Z',
}
const declaredStaffView: ClinicalHistoryEntry = {
  ...base, view: 'staff', id: 'e1', category: 'allergy', name: 'Penicilina sintética', severity: 'unknown',
  origin: 'patient_declared', confirmed: false, version: 2, created_by_name: 'Paciente', hidden: false, hidden_at: null,
  hidden_reason: null, hidden_by_name: null,
}
const hiddenStaffView: ClinicalHistoryEntry = {
  ...base, view: 'staff', id: 'e2', category: 'condition', name: 'Asma sintética', condition_status: 'resolved', onset: '2010',
  resolved: '2015-03', origin: 'professional', confirmed: true, confirmed_by_name: 'Dra. Rita', version: 4,
  created_by_name: 'Dra. Rita', hidden: true, hidden_at: '2026-10-02T10:00:00Z', hidden_reason: 'Motivo sintético', hidden_by_name: 'Dra. Rita',
}

type Callbacks = { onSuccess?: () => void; onError?: (error: unknown) => void }
const lastCall = () => h.mutate.mock.calls.at(-1) as [unknown, Callbacks]

beforeEach(() => {
  h.entries = []
  h.mutate.mockReset()
})

describe('ClinicalHistorySection for doctors and nurses', () => {
  it('shows origin, partial dates and hidden entries with their reason', () => {
    h.entries = [declaredStaffView, hiddenStaffView]
    render(<ClinicalHistorySection patientId="p1" mode="staff" />)
    const conditions = screen.getByRole('region', { name: 'Doenças e problemas de saúde' })
    expect(conditions).toHaveTextContent('Resolvida · Início 2010 · Resolvida março 2015')
    expect(conditions).toHaveTextContent('Confirmado pelo profissional')
    expect(conditions).toHaveTextContent('Oculto ao paciente')
    expect(conditions).toHaveTextContent('Motivo para ocultar: Motivo sintético (Dra. Rita)')
    expect(within(conditions).getByRole('button', { name: 'Mostrar ao paciente' })).toBeInTheDocument()
    const allergies = screen.getByRole('region', { name: 'Alergias' })
    expect(allergies).toHaveTextContent('Declarado pelo paciente')
    expect(within(allergies).getByRole('button', { name: 'Confirmar' })).toBeInTheDocument()
  })

  it('adds an entry with a partial date and the fields of its category only', async () => {
    const user = userEvent.setup()
    render(<ClinicalHistorySection patientId="p1" mode="staff" />)
    const procedures = screen.getByRole('region', { name: 'Cirurgias e procedimentos' })
    await user.click(within(procedures).getByRole('button', { name: 'Adicionar cirurgia ou procedimento' }))
    const form = within(procedures).getByRole('form')
    await user.click(within(form).getByRole('button', { name: 'Adicionar cirurgia ou procedimento' }))
    expect(within(form).getByText('Campo obrigatório.')).toBeInTheDocument()
    expect(h.mutate).not.toHaveBeenCalled()

    await user.type(within(form).getByLabelText('Cirurgia ou procedimento'), 'Apendicectomia')
    await user.selectOptions(within(form).getByLabelText('Data: precisão'), 'month')
    await user.type(within(form).getByLabelText('Data: mês'), '2012-06')
    await user.type(within(form).getByLabelText('Local (opcional)'), 'Hospital Sintético')
    await user.click(within(form).getByRole('button', { name: 'Adicionar cirurgia ou procedimento' }))
    expect(lastCall()[0]).toEqual({
      kind: 'create',
      payload: { category: 'procedure', name: 'Apendicectomia', occurred: '2012-06', location: 'Hospital Sintético' },
    })
    act(() => lastCall()[1].onSuccess?.())
    expect(screen.getByRole('status')).toHaveTextContent('Entrada adicionada.')
  })

  it('confirms with the current version and shows a stale-version conflict', async () => {
    h.entries = [declaredStaffView]
    const user = userEvent.setup()
    render(<ClinicalHistorySection patientId="p1" mode="staff" />)
    await user.click(screen.getByRole('button', { name: 'Confirmar' }))
    expect(lastCall()[0]).toEqual({ kind: 'confirm', id: 'e1', version: 2 })
    act(() => lastCall()[1].onError?.(new ApiError(409, 'x', { detail: 'A entrada foi alterada entretanto.' })))
    expect(screen.getByRole('alert')).toHaveTextContent('A entrada foi alterada entretanto.')
  })

  it('hides from the patient and deletes only with a reason', async () => {
    h.entries = [declaredStaffView]
    const user = userEvent.setup()
    render(<ClinicalHistorySection patientId="p1" mode="staff" />)

    await user.click(screen.getByRole('button', { name: 'Ocultar ao paciente' }))
    let dialog = screen.getByRole('alertdialog', { name: 'Ocultar ao paciente' })
    await user.click(within(dialog).getByRole('button', { name: 'Ocultar' }))
    expect(within(dialog).getByText('Indica o motivo.')).toBeInTheDocument()
    expect(h.mutate).not.toHaveBeenCalled()
    await user.type(within(dialog).getByLabelText('Motivo'), 'Motivo sintético')
    await user.click(within(dialog).getByRole('button', { name: 'Ocultar' }))
    expect(lastCall()[0]).toEqual({ kind: 'hide', id: 'e1', version: 2, reason: 'Motivo sintético' })
    act(() => lastCall()[1].onSuccess?.())

    await user.click(screen.getByRole('button', { name: 'Apagar' }))
    dialog = screen.getByRole('alertdialog', { name: 'Apagar entrada' })
    await user.click(within(dialog).getByRole('button', { name: 'Apagar' }))
    expect(within(dialog).getByText('Indica o motivo.')).toBeInTheDocument()
    await user.type(within(dialog).getByLabelText('Motivo'), 'Registo duplicado')
    await user.click(within(dialog).getByRole('button', { name: 'Apagar' }))
    expect(lastCall()[0]).toEqual({ kind: 'remove', id: 'e1', version: 2, reason: 'Registo duplicado' })
  })

  it('edits with the expected version and shows backend field errors next to the field', async () => {
    h.entries = [hiddenStaffView]
    const user = userEvent.setup()
    render(<ClinicalHistorySection patientId="p1" mode="staff" />)
    await user.click(screen.getByRole('button', { name: 'Editar' }))
    const form = screen.getByRole('form')
    expect(within(form).getByLabelText('Início: precisão')).toHaveValue('year')
    expect(within(form).getByLabelText('Início: ano')).toHaveValue(2010)
    await user.selectOptions(within(form).getByLabelText('Estado'), 'active')
    await user.click(within(form).getByRole('button', { name: 'Guardar alterações' }))
    expect(lastCall()[0]).toEqual({
      kind: 'update',
      id: 'e2',
      payload: { name: 'Asma sintética', condition_status: 'active', onset: '2010', resolved: null, expected_version: 4 },
    })
    act(() => lastCall()[1].onError?.(new ApiError(422, 'x', { fieldErrors: { name: 'Campo obrigatório.' } })))
    expect(within(screen.getByRole('form')).getByText('Campo obrigatório.')).toBeInTheDocument()
  })
})

describe('ClinicalHistorySection for the patient', () => {
  const ownDeclaration: ClinicalHistoryEntry = {
    ...base, view: 'patient', id: 'p-own', category: 'immunization', name: 'Tétano', occurred: '2020-05',
    origin: 'patient_declared', confirmed: false, version: 1, can_edit: true,
  }
  const confirmed: ClinicalHistoryEntry = {
    ...base, view: 'patient', id: 'p-conf', category: 'note', note_text: 'Nota sintética', origin: 'professional',
    confirmed: true, confirmed_by_name: 'Dra. Rita', version: 1, can_edit: false,
  }

  it('declares, edits and removes only unconfirmed declarations, with no staff actions', async () => {
    h.entries = [ownDeclaration, confirmed]
    const user = userEvent.setup()
    render(<ClinicalHistorySection patientId="p1" mode="patient" />)
    const notes = screen.getByRole('region', { name: 'Outras notas' })
    expect(notes).toHaveTextContent('Confirmado pelo profissional')
    expect(within(notes).queryByRole('button', { name: 'Editar' })).not.toBeInTheDocument()
    for (const name of ['Confirmar', 'Ocultar ao paciente', 'Mostrar ao paciente']) {
      expect(screen.queryByRole('button', { name })).not.toBeInTheDocument()
    }

    const vaccines = screen.getByRole('region', { name: 'Vacinas' })
    expect(vaccines).toHaveTextContent('maio 2020')
    expect(vaccines).toHaveTextContent('Declarado pelo paciente')
    await user.click(within(vaccines).getByRole('button', { name: 'Apagar' }))
    const dialog = screen.getByRole('alertdialog', { name: 'Apagar declaração' })
    expect(within(dialog).queryByLabelText('Motivo')).not.toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Apagar' }))
    expect(lastCall()[0]).toEqual({ kind: 'remove', id: 'p-own', version: 1, reason: undefined })

    const allergies = screen.getByRole('region', { name: 'Alergias' })
    await user.click(within(allergies).getByRole('button', { name: 'Declarar alergia' }))
    expect(within(allergies).getByText(/Fica como «Declarado pelo paciente»/)).toBeInTheDocument()
    await user.type(within(allergies).getByLabelText('Substância'), 'Pólen')
    await user.selectOptions(within(allergies).getByLabelText('Gravidade'), 'mild')
    await user.click(within(allergies).getByRole('button', { name: 'Declarar alergia' }))
    expect(lastCall()[0]).toEqual({ kind: 'create', payload: { category: 'allergy', name: 'Pólen', reaction: null, severity: 'mild' } })
  })
})
