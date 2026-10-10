import { act, render, screen, within } from '@testing-library/react'
import type { ReactElement } from 'react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ClinicalResultsSection } from './ClinicalResultsSection'
import { ApiError } from '../lib/apiClient'
import type { ClinicalResultPatientView, ClinicalResultPublic, ClinicalResultStaffView } from '../types/api'

type Query = { data: unknown; isLoading: boolean; isError: boolean; error: unknown; refetch: () => void }
type Options = { onSuccess?: (value?: unknown) => void; onError?: (error: unknown) => void }

const h = vi.hoisted(() => ({
  list: { data: undefined as unknown, isLoading: false, isError: false, error: null as unknown, refetch: vi.fn() } as Query,
  single: { data: undefined as unknown, isLoading: false, isError: false, error: null as unknown, refetch: vi.fn() } as Query,
  singleRequested: [] as Array<string | null>,
  create: { mutate: vi.fn(), isPending: false },
  update: { mutate: vi.fn(), isPending: false },
  release: { mutate: vi.fn(), isPending: false },
  correct: { mutate: vi.fn(), isPending: false },
}))

vi.mock('../hooks/useClinicalResults', () => ({
  useClinicalResults: () => h.list,
  useClinicalResult: (id: string | null) => { h.singleRequested.push(id); return id ? h.single : { ...h.single, data: undefined, isError: false } },
  useCreateClinicalResult: () => h.create,
  useUpdateClinicalResult: () => h.update,
  useReleaseClinicalResult: () => h.release,
  useCorrectClinicalResult: () => h.correct,
}))

vi.mock('../hooks/useDocuments', () => ({
  usePatientDocuments: () => ({
    data: { items: [{ id: 'doc-1', title: 'Relatório do laboratório' }], total: 1 },
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
}))

const released: ClinicalResultPatientView = {
  view: 'patient',
  id: 'res-1',
  category: 'laboratory',
  title: 'Hemoglobina',
  value: '13.5',
  unit: 'g/dL',
  reference_range: '12-16',
  summary: 'Dentro dos valores normais.',
  result_date: '2026-09-20',
  document_id: 'doc-1',
  author_name: 'Dra. Rita Sousa',
  released_at: '2026-09-21T10:00:00Z',
  corrects_result_id: null,
  superseded_by_result_id: null,
}

const draft: ClinicalResultStaffView = {
  view: 'staff',
  id: 'res-2',
  patient_id: 'patient-1',
  category: 'imaging',
  title: 'RX tórax',
  value: null,
  unit: null,
  reference_range: null,
  summary: 'Sem alterações.',
  result_date: '2026-09-22',
  document_id: null,
  status: 'draft',
  author_name: 'Dra. Rita Sousa',
  released_at: null,
  released_by_name: null,
  corrects_result_id: null,
  correction_reason: null,
  corrected_by_result_id: null,
  superseded: false,
  created_at: '2026-09-22T10:00:00Z',
  updated_at: '2026-09-22T10:00:00Z',
}

function page(items: ClinicalResultPublic[], total = items.length): Query {
  return { data: { items, total }, isLoading: false, isError: false, error: null, refetch: vi.fn() }
}

function renderSection(ui: ReactElement, url = '/patient/resultados') {
  return render(<MemoryRouter initialEntries={[url]}>{ui}</MemoryRouter>)
}

describe('ClinicalResultsSection', () => {
  beforeEach(() => {
    h.list = page([released])
    h.single = { data: undefined, isLoading: false, isError: false, error: null, refetch: vi.fn() }
    h.singleRequested = []
    h.create = { mutate: vi.fn(), isPending: false }
    h.update = { mutate: vi.fn(), isPending: false }
    h.release = { mutate: vi.fn(), isPending: false }
    h.correct = { mutate: vi.fn(), isPending: false }
  })

  it('shows the loading state', () => {
    h.list = { data: undefined, isLoading: true, isError: false, error: null, refetch: vi.fn() }
    renderSection(<ClinicalResultsSection patientId="patient-1" canManage={false} patientArea />)
    expect(screen.getByText('A carregar resultados…')).toBeInTheDocument()
  })

  it('shows a patient-oriented empty state', () => {
    h.list = page([])
    renderSection(<ClinicalResultsSection patientId="patient-1" canManage={false} patientArea />)
    expect(screen.getByText('Ainda não existem resultados disponíveis na tua ficha.')).toBeInTheDocument()
  })

  it('shows a retryable error state', async () => {
    const user = userEvent.setup()
    h.list = { data: undefined, isLoading: false, isError: true, error: new ApiError(500, 'x'), refetch: vi.fn() }
    renderSection(<ClinicalResultsSection patientId="patient-1" canManage={false} patientArea />)
    await user.click(screen.getByRole('button', { name: /tentar/i }))
    expect(h.list.refetch).toHaveBeenCalled()
  })

  it('is read-only for the patient and opens the detail with the linked document', async () => {
    const user = userEvent.setup()
    renderSection(<ClinicalResultsSection patientId="patient-1" canManage={false} patientArea />)
    const list = screen.getByRole('list', { name: 'Lista de resultados' })
    expect(within(list).getByText('Hemoglobina')).toBeInTheDocument()
    expect(within(list).getByText(/13\.5 g\/dL \(referência: 12-16\)/)).toBeInTheDocument()
    expect(screen.queryByRole('form', { name: 'Registar resultado' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Disponibilizar' })).not.toBeInTheDocument()
    expect(screen.queryByText('Rascunho')).not.toBeInTheDocument()

    await user.click(within(list).getByRole('button', { name: 'Ver detalhe' }))
    expect(within(list).getByText('Dentro dos valores normais.')).toBeInTheDocument()
    expect(within(list).getByRole('link', { name: 'Abrir documento' })).toHaveAttribute('href', '/patient/documentos?document=doc-1')
  })

  it('highlights and opens the result named by a notification deep link', () => {
    renderSection(<ClinicalResultsSection patientId="patient-1" canManage={false} patientArea />, '/patient/resultados?result=res-1')
    const row = screen.getByText('Hemoglobina').closest('li') as HTMLElement
    expect(row).toHaveAttribute('aria-current', 'true')
    expect(within(row).getByText('Dentro dos valores normais.')).toBeInTheDocument()
    // Already on the page: no extra request for the single result.
    expect(h.singleRequested.every((id) => id === null)).toBe(true)
  })

  it('loads a deep-linked result that is not on the current page, and hides access details on denial', () => {
    h.single = { data: undefined, isLoading: false, isError: true, error: new ApiError(404, 'x'), refetch: vi.fn() }
    renderSection(<ClinicalResultsSection patientId="patient-1" canManage={false} patientArea />, '/patient/resultados?result=res-9')
    expect(h.singleRequested).toContain('res-9')
    expect(screen.getByRole('alert')).toHaveTextContent('Não tens acesso a este resultado ou ele já não está disponível.')
  })

  it('shows workflow state and releases a draft after confirmation', async () => {
    const user = userEvent.setup()
    h.list = page([draft, { ...draft, id: 'res-3', title: 'Glicemia', status: 'released', released_at: '2026-09-23T10:00:00Z', released_by_name: 'Enf. João Lima' }])
    renderSection(<ClinicalResultsSection patientId="patient-1" canManage />, '/app/pacientes/patient-1')
    expect(screen.getByText('Rascunho')).toBeInTheDocument()
    expect(screen.getByText('Disponibilizado')).toBeInTheDocument()
    // Only the draft can be edited or released.
    expect(screen.getAllByRole('button', { name: 'Disponibilizar' })).toHaveLength(1)
    expect(screen.getAllByRole('button', { name: 'Editar' })).toHaveLength(1)

    await user.click(screen.getByRole('button', { name: 'Disponibilizar' }))
    const dialog = screen.getByRole('alertdialog')
    expect(dialog).toHaveTextContent('notificação genérica')
    await user.click(within(dialog).getByRole('button', { name: 'Disponibilizar' }))
    expect(h.release.mutate).toHaveBeenCalledWith('res-2', expect.any(Object))
    const options = h.release.mutate.mock.calls[0][1] as Options
    act(() => options.onSuccess?.())
    expect(screen.getByRole('status')).toHaveTextContent('Resultado disponibilizado ao paciente.')
  })

  it('reports a release conflict with the backend reason', async () => {
    const user = userEvent.setup()
    h.list = page([draft])
    renderSection(<ClinicalResultsSection patientId="patient-1" canManage />, '/app/pacientes/patient-1')
    await user.click(screen.getByRole('button', { name: 'Disponibilizar' }))
    await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Disponibilizar' }))
    const options = h.release.mutate.mock.calls[0][1] as Options
    act(() => options.onError?.(new ApiError(409, 'x', { detail: 'Este resultado já foi disponibilizado ao paciente.' })))
    expect(screen.getByRole('alert')).toHaveTextContent('Este resultado já foi disponibilizado ao paciente.')
  })

  it('validates the form and sends no request when content is missing', async () => {
    const user = userEvent.setup()
    h.list = page([])
    renderSection(<ClinicalResultsSection patientId="patient-1" canManage />, '/app/pacientes/patient-1')
    const form = screen.getByRole('form', { name: 'Registar resultado' })
    await user.click(within(form).getByRole('button', { name: 'Registar resultado' }))
    expect(within(form).getByText('Indica a designação do resultado.')).toBeInTheDocument()
    expect(within(form).getByText('Indica a data do resultado.')).toBeInTheDocument()
    expect(within(form).getByText('Indica um valor, um resumo ou um documento associado.')).toBeInTheDocument()
    expect(h.create.mutate).not.toHaveBeenCalled()
  })

  it('creates a draft by default and can release it immediately', async () => {
    const user = userEvent.setup()
    h.list = page([])
    renderSection(<ClinicalResultsSection patientId="patient-1" canManage />, '/app/pacientes/patient-1')
    const form = screen.getByRole('form', { name: 'Registar resultado' })
    await user.type(within(form).getByLabelText(/Designação/), 'Hemoglobina')
    await user.type(within(form).getByLabelText('Valor'), '13.5')
    await user.type(within(form).getByLabelText('Unidade'), 'g/dL')
    await user.type(within(form).getByLabelText(/Data do resultado/), '2026-09-20')
    await user.selectOptions(within(form).getByLabelText('Documento associado (opcional)'), 'doc-1')
    await user.click(within(form).getByRole('button', { name: 'Registar resultado' }))
    expect(h.create.mutate).toHaveBeenLastCalledWith(
      {
        category: 'laboratory',
        title: 'Hemoglobina',
        value: '13.5',
        unit: 'g/dL',
        reference_range: undefined,
        summary: undefined,
        result_date: '2026-09-20',
        document_id: 'doc-1',
        release: false,
      },
      expect.any(Object),
    )
    await user.click(within(form).getByRole('checkbox', { name: 'Disponibilizar já ao paciente' }))
    await user.click(within(form).getByRole('button', { name: 'Registar resultado' }))
    expect(h.create.mutate).toHaveBeenLastCalledWith(expect.objectContaining({ release: true }), expect.any(Object))
  })

  it('edits a draft, clearing removed optional fields explicitly', async () => {
    const user = userEvent.setup()
    h.list = page([{ ...draft, value: '5', unit: 'mg' }])
    renderSection(<ClinicalResultsSection patientId="patient-1" canManage />, '/app/pacientes/patient-1')
    await user.click(screen.getByRole('button', { name: 'Editar' }))
    const form = screen.getByRole('form', { name: 'Editar resultado' })
    await user.clear(within(form).getByLabelText('Unidade'))
    await user.clear(within(form).getByLabelText('Valor'))
    await user.click(within(form).getByRole('button', { name: 'Guardar rascunho' }))
    expect(h.update.mutate).toHaveBeenCalledWith(
      {
        id: 'res-2',
        payload: {
          category: 'imaging',
          title: 'RX tórax',
          value: null,
          unit: null,
          reference_range: null,
          summary: 'Sem alterações.',
          result_date: '2026-09-22',
          document_id: null,
        },
      },
      expect.any(Object),
    )
  })

  describe('corrections', () => {
    const releasedStaff: ClinicalResultStaffView = {
      ...draft,
      id: 'res-3',
      category: 'laboratory',
      title: 'Glicemia',
      value: '180',
      unit: 'mg/dL',
      status: 'released',
      released_at: '2026-09-23T10:00:00Z',
      released_by_name: 'Enf. João Lima',
    }

    it('offers a correction, never an edit, for a released result', async () => {
      const user = userEvent.setup()
      h.list = page([releasedStaff, { ...releasedStaff, id: 'res-4', title: 'Ureia', corrected_by_result_id: 'res-5' }])
      renderSection(<ClinicalResultsSection patientId="patient-1" canManage />, '/app/pacientes/patient-1')
      expect(screen.queryByRole('button', { name: 'Editar' })).not.toBeInTheDocument()
      // A result that already has a correction is corrected through its latest version.
      expect(screen.getAllByRole('button', { name: 'Registar correção' })).toHaveLength(1)
      expect(screen.getByText('Correção em rascunho')).toBeInTheDocument()

      await user.click(screen.getByRole('button', { name: 'Registar correção' }))
      const form = screen.getByRole('form', { name: 'Registar correção' })
      expect(form).toHaveTextContent('O resultado original não é alterado')
      expect(within(form).getByLabelText(/Designação/)).toHaveValue('Glicemia')
      await user.click(within(form).getByRole('button', { name: 'Registar correção' }))
      expect(within(form).getByText(/Indica o motivo da correção/)).toBeInTheDocument()
      expect(h.correct.mutate).not.toHaveBeenCalled()

      const value = within(form).getByLabelText('Valor')
      await user.clear(value)
      await user.type(value, '108')
      await user.type(within(form).getByLabelText(/Motivo da correção/), '  Erro de transcrição  ')
      await user.click(within(form).getByRole('button', { name: 'Registar correção' }))
      expect(h.correct.mutate).toHaveBeenCalledWith(
        {
          id: 'res-3',
          payload: expect.objectContaining({ title: 'Glicemia', value: '108', unit: 'mg/dL', correction_reason: 'Erro de transcrição', release: false }),
        },
        expect.any(Object),
      )
      const options = h.correct.mutate.mock.calls[0][1] as Options
      act(() => options.onSuccess?.({ ...releasedStaff, status: 'draft' }))
      expect(screen.getByRole('status')).toHaveTextContent('O resultado original mantém-se inalterado.')
    })

    it('edits a draft correction including its reason and explains its release', async () => {
      const user = userEvent.setup()
      const correction = { ...draft, id: 'res-6', corrects_result_id: 'res-3', correction_reason: 'Erro de transcrição' }
      h.list = page([correction])
      renderSection(<ClinicalResultsSection patientId="patient-1" canManage />, '/app/pacientes/patient-1')
      expect(screen.getByText('Correção')).toBeInTheDocument()
      await user.click(screen.getByRole('button', { name: 'Ver detalhe' }))
      expect(screen.getByText('Motivo da correção (interno)')).toBeInTheDocument()
      await user.click(screen.getByRole('button', { name: 'Editar' }))
      const form = screen.getByRole('form', { name: 'Editar correção' })
      await user.click(within(form).getByRole('button', { name: 'Guardar rascunho' }))
      expect(h.update.mutate).toHaveBeenCalledWith(
        { id: 'res-6', payload: expect.objectContaining({ correction_reason: 'Erro de transcrição' }) },
        expect.any(Object),
      )
      await user.click(within(form).getByRole('button', { name: 'Cancelar edição' }))
      await user.click(screen.getByRole('button', { name: 'Disponibilizar' }))
      expect(screen.getByRole('alertdialog')).toHaveTextContent('O motivo da correção não lhe é mostrado.')
    })

    it('shows the patient both versions, linked, without the internal reason', async () => {
      const user = userEvent.setup()
      const corrected: ClinicalResultPatientView = { ...released, superseded_by_result_id: 'res-7' }
      const correction: ClinicalResultPatientView = { ...released, id: 'res-7', value: '12.9', corrects_result_id: 'res-1' }
      h.list = page([correction, corrected])
      renderSection(<ClinicalResultsSection patientId="patient-1" canManage={false} patientArea />)
      expect(screen.getByText('Corrigido')).toBeInTheDocument()
      expect(screen.getByText('Correção')).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Registar correção' })).not.toBeInTheDocument()
      const [correctionRow, correctedRow] = screen.getAllByRole('listitem')
      await user.click(within(correctionRow).getByRole('button', { name: 'Ver detalhe' }))
      expect(within(correctionRow).getByRole('link', { name: 'Ver o resultado original' })).toHaveAttribute('href', '/patient/resultados?result=res-1')
      expect(screen.queryByText(/Motivo da correção/)).not.toBeInTheDocument()
      await user.click(within(correctedRow).getByRole('button', { name: 'Ver detalhe' }))
      expect(within(correctedRow).getByRole('link', { name: 'Ver a versão corrigida' })).toHaveAttribute('href', '/patient/resultados?result=res-7')
      // What the patient was originally shown is still displayed.
      expect(within(correctedRow).getByText(/13\.5 g\/dL/)).toBeInTheDocument()
    })
  })
})
